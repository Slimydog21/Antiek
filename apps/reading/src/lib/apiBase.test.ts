/**
 * The API-base resolution contract.
 *
 * In production the app is served from Cloudflare Pages while the substrate
 * answers on a different origin, and Pages proxies nothing. A bare "/speak/..."
 * therefore resolves against the Pages origin and returns the SPA shell instead
 * of the API. The Vite dev proxy hides this locally, so the failure is invisible
 * in development and total in production — which is why it is pinned here.
 */
import { describe, expect, it, vi, afterEach } from "vitest";

async function withBase<T>(base: string, fn: (m: typeof import("./api")) => T): Promise<T> {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE_URL", base);
  const mod = await import("./api");
  return fn(mod);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("resolveApiUrl", () => {
  it("prefixes a root-relative path when a base is configured", async () => {
    await withBase("https://api.antiek.test", ({ resolveApiUrl }) => {
      expect(resolveApiUrl("/speak/projects")).toBe("https://api.antiek.test/speak/projects");
      expect(resolveApiUrl("/loop-3/status")).toBe("https://api.antiek.test/loop-3/status");
    });
  });

  it("leaves paths untouched when no base is configured, so the dev proxy still works", async () => {
    await withBase("", ({ resolveApiUrl }) => {
      expect(resolveApiUrl("/speak/projects")).toBe("/speak/projects");
    });
  });

  it("is idempotent: an already-prefixed URL is not prefixed twice", async () => {
    await withBase("https://api.antiek.test", ({ resolveApiUrl, API_BASE }) => {
      const once = `${API_BASE}/health`;
      expect(resolveApiUrl(once)).toBe(once);
      expect(resolveApiUrl(resolveApiUrl("/health"))).toBe("https://api.antiek.test/health");
    });
  });

  it("leaves absolute and protocol-relative URLs alone", async () => {
    await withBase("https://api.antiek.test", ({ resolveApiUrl }) => {
      expect(resolveApiUrl("https://elsewhere.test/x")).toBe("https://elsewhere.test/x");
      expect(resolveApiUrl("http://elsewhere.test/x")).toBe("http://elsewhere.test/x");
      // "//host/path" is a real absolute URL, not a root-relative path.
      expect(resolveApiUrl("//cdn.test/x")).toBe("//cdn.test/x");
    });
  });

  it("leaves a relative path with no leading slash alone", async () => {
    await withBase("https://api.antiek.test", ({ resolveApiUrl }) => {
      expect(resolveApiUrl("relative/path")).toBe("relative/path");
    });
  });
});

describe("apiFetch", () => {
  it("resolves a string path and keeps credentials on every call", async () => {
    await withBase("https://api.antiek.test", async ({ apiFetch }) => {
      const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
      await apiFetch("/speak/projects");
      expect(spy).toHaveBeenCalledWith(
        "https://api.antiek.test/speak/projects",
        expect.objectContaining({ credentials: "include" }),
      );
      spy.mockRestore();
    });
  });

  it("passes a Request through untouched rather than rebuilding it", async () => {
    await withBase("https://api.antiek.test", async ({ apiFetch }) => {
      const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
      const req = new Request("https://api.antiek.test/x", { method: "POST", body: "payload" });
      await apiFetch(req);
      // Rebuilding a Request here would silently drop its body.
      expect(spy.mock.calls[0][0]).toBe(req);
      spy.mockRestore();
    });
  });
});
