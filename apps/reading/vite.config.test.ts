// @vitest-environment node
//
// A-19 (FFX SPR-05): the dev proxy must hand browser navigations on SPA
// routes to the SPA, keep API fetches on the proxy, and point /ws at the
// same backend as HTTP. These tests exercise the exported functions and the
// real exported config, so a regression in either shows up here.
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProxyOptions, UserConfig } from "vite";
import { spaNavigationBypass, wsTargetFor } from "./vite.config";

type Req = Parameters<typeof spaNavigationBypass>[0];
const req = (accept: string | undefined, method = "GET", url = "/sources"): Req =>
  ({ method, url, headers: accept === undefined ? {} : { accept } }) as Req;

async function loadConfig(env: Record<string, string | undefined>) {
  vi.resetModules();
  for (const [k, v] of Object.entries(env)) vi.stubEnv(k, v as string);
  const mod = await import("./vite.config");
  const config = mod.default as UserConfig;
  // resetModules gives a fresh module instance; identity checks use ITS bypass.
  return {
    proxy: config.server!.proxy! as Record<string, string | ProxyOptions>,
    bypass: mod.spaNavigationBypass,
  };
}

// Vite treats a string proxy entry as { target: string, changeOrigin: true }.
const targetOf = (opts: string | ProxyOptions | undefined) =>
  typeof opts === "string" ? opts : opts?.target;

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("spaNavigationBypass (M1)", () => {
  it("bypasses a browser navigation (Accept: text/html) to the SPA, URL untouched", () => {
    expect(spaNavigationBypass(req("text/html"))).toBe("/sources");
    expect(
      spaNavigationBypass(
        req("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "GET", "/write/dlv-1?x=1"),
      ),
    ).toBe("/write/dlv-1?x=1");
    expect(spaNavigationBypass(req("text/html", "HEAD"))).toBe("/sources");
  });

  it("proxies a JSON fetch", () => {
    expect(spaNavigationBypass(req("application/json"))).toBeUndefined();
  });

  it("proxies a request with no Accept header", () => {
    expect(spaNavigationBypass(req(undefined))).toBeUndefined();
  });

  it("proxies a fetch() default Accept of */*", () => {
    expect(spaNavigationBypass(req("*/*"))).toBeUndefined();
  });

  it("matches the Accept media type case-insensitively (RFC 9110 §8.3.1)", () => {
    expect(spaNavigationBypass(req("Text/HTML"))).toBe("/sources");
    expect(spaNavigationBypass(req("TEXT/HTML,*/*;q=0.8"))).toBe("/sources");
    expect(spaNavigationBypass(req("Application/JSON"))).toBeUndefined();
  });

  it("never bypasses a non-GET/HEAD request, even one that accepts HTML", () => {
    expect(spaNavigationBypass(req("text/html", "POST", "/sources/upload"))).toBeUndefined();
  });
});

describe("wsTargetFor (M2)", () => {
  it.each([
    ["http://127.0.0.1:8017", "ws://127.0.0.1:8017"],
    ["HTTP://127.0.0.1:8017", "ws://127.0.0.1:8017"],
    ["https://api.example.test", "wss://api.example.test"],
    ["HTTPS://api.example.test", "wss://api.example.test"],
    ["HttpS://api.example.test:8443", "wss://api.example.test:8443"],
  ])("maps %s to %s (scheme normalised, host and port kept)", (input, expected) => {
    expect(wsTargetFor(input)).toBe(expected);
  });
});

describe("exported dev config", () => {
  it("derives the /ws target from ANTIEK_DEV_API_TARGET", async () => {
    const { proxy } = await loadConfig({ ANTIEK_DEV_API_TARGET: "http://127.0.0.1:8017" });
    const ws = proxy["/ws"] as ProxyOptions;
    expect(ws.target).toBe("ws://127.0.0.1:8017");
    expect(ws.ws).toBe(true);
    expect(targetOf(proxy["/health"])).toBe("http://127.0.0.1:8017");
  });

  it.each([
    ["unset", undefined],
    ["empty", ""],
  ])("defaults both HTTP and /ws to 127.0.0.1:8000 when the var is unset or empty (%s)", async (_label, value) => {
    const { proxy } = await loadConfig({ ANTIEK_DEV_API_TARGET: value });
    expect(targetOf(proxy["/ws"])).toBe("ws://127.0.0.1:8000");
    expect(targetOf(proxy["/health"])).toBe("http://127.0.0.1:8000");
  });

  it("puts the bypass on exactly the proxy prefixes that shadow an SPA route in App.tsx", async () => {
    const { proxy, bypass: loadedBypass } = await loadConfig({
      ANTIEK_DEV_API_TARGET: "http://127.0.0.1:8017",
    });
    expect(typeof loadedBypass).toBe("function");
    const appTsx = readFileSync(path.resolve(__dirname, "src/App.tsx"), "utf8");
    const spaPaths = [...appTsx.matchAll(/<Route[^>]*\spath="([^"]+)"/g)].map((m) => m[1]);
    expect(spaPaths.length).toBeGreaterThan(20);

    // Vite matches a string proxy context with url.startsWith(context).
    const shadowing = Object.keys(proxy)
      .filter((prefix) => spaPaths.some((p) => p.startsWith(prefix)))
      .sort();
    expect(shadowing).toEqual(["/investigations", "/library", "/notebooks", "/sources", "/speak", "/write"]);

    for (const [prefix, opts] of Object.entries(proxy)) {
      const bypass = typeof opts === "string" ? undefined : opts.bypass;
      if (shadowing.includes(prefix)) {
        expect(bypass, prefix).toBe(loadedBypass);
      } else {
        // e.g. /auth/callback and /auth/dev-login ARE browser navigations that
        // must reach the API; a blanket bypass would break sign-in.
        expect(bypass, prefix).toBeUndefined();
      }
    }
  });

  it("proxies Speak API calls while keeping invitation navigations in the SPA", async () => {
    const { proxy, bypass } = await loadConfig({ ANTIEK_DEV_API_TARGET: "http://127.0.0.1:8017" });
    const speak = proxy["/speak"];
    expect(typeof speak).toBe("object");
    if (!speak || typeof speak === "string") throw new Error("Speak proxy missing");
    expect(speak.target).toBe("http://127.0.0.1:8017");
    expect(speak.bypass).toBe(bypass);
    expect(bypass(req("text/html", "GET", "/speak/invite/token"))).toBe("/speak/invite/token");
    expect(bypass(req("*/*", "GET", "/speak/feed"))).toBeUndefined();
    expect(bypass(req("*/*", "POST", "/speak/invite/token/voice"))).toBeUndefined();
  });
});
