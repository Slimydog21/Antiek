/**
 * The pre-paint boot script in index.html, run as written. It is the only
 * code that runs before first paint, so it must resolve the same theme the
 * React side (theme.ts) would, survive blocked storage, and paint the browser
 * chrome in the page ground the tokens define.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolvedTheme, themePreference } from "./theme";
import { semantic } from "./tokens";

const here = dirname(fileURLToPath(import.meta.url));
const indexHtml = readFileSync(join(here, "..", "..", "index.html"), "utf8");
/** Every <script> without a src, whatever its attributes: code that runs before the app. */
const inlineScripts = [...indexHtml.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
  .filter((m) => !/\bsrc\s*=/.test(m[1]))
  .map((m) => m[2]);
const bootSource = inlineScripts[0] ?? "";

const html = document.documentElement;
let changeListener: (() => void) | null = null;

function boot({ stored = {} as Record<string, string>, osDark = false, blocked = false } = {}) {
  for (const a of ["data-theme", "data-theme-pref", "data-motion"]) html.removeAttribute(a);
  document.head.innerHTML = '<meta name="theme-color" content="" />';
  window.localStorage.clear();
  for (const [k, v] of Object.entries(stored)) window.localStorage.setItem(k, v);
  if (blocked) {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
  }
  const os = { dark: osDark };
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      get matches() {
        return q.includes("dark") ? os.dark : false;
      },
      addEventListener: (_: string, cb: () => void) => {
        changeListener = cb;
      },
    }),
  });
  new Function(bootSource)();
  return os;
}

const meta = () => document.querySelector('meta[name="theme-color"]')?.getAttribute("content");

afterEach(() => {
  vi.restoreAllMocks();
  changeListener = null;
  window.localStorage.clear();
  for (const a of ["data-theme", "data-theme-pref", "data-motion"]) html.removeAttribute(a);
});

describe("index.html boot script (runs before first paint)", () => {
  it("has exactly one inline script, and it is the theme boot", () => {
    expect(inlineScripts).toHaveLength(1);
    expect(bootSource).toContain("antiek.theme");
    expect(bootSource).toContain("antiek.motion");
  });

  it("defaults to system: follows the OS, and keeps following it", () => {
    const os = boot({ osDark: true });
    expect(html.getAttribute("data-theme-pref")).toBe("system");
    expect(html.getAttribute("data-theme")).toBe("dark");
    os.dark = false;
    changeListener?.();
    expect(html.getAttribute("data-theme")).toBe("light");
  });

  it("an explicit preference wins over the OS and does not follow it", () => {
    const os = boot({ stored: { "antiek.theme": "light" }, osDark: true });
    expect(html.getAttribute("data-theme")).toBe("light");
    os.dark = true;
    changeListener?.();
    expect(html.getAttribute("data-theme")).toBe("light");
  });

  it("ignores junk values and blocked storage (private window) instead of throwing", () => {
    boot({ stored: { "antiek.theme": "purple", "antiek.motion": "fast" } });
    expect(html.getAttribute("data-theme-pref")).toBe("system");
    expect(html.hasAttribute("data-motion")).toBe(false);
    expect(() => boot({ blocked: true, osDark: true })).not.toThrow();
    expect(html.getAttribute("data-theme")).toBe("dark");
  });

  it("marks <html data-motion> for an in-app motion choice", () => {
    boot({ stored: { "antiek.motion": "reduce" } });
    expect(html.getAttribute("data-motion")).toBe("reduce");
  });

  it("agrees with theme.ts on every preference x OS combination", () => {
    for (const pref of ["light", "dark", undefined]) {
      for (const osDark of [false, true]) {
        boot({ stored: pref ? { "antiek.theme": pref } : {}, osDark });
        const bootTheme = html.getAttribute("data-theme");
        expect(themePreference()).toBe(pref ?? "system");
        expect(resolvedTheme(), `pref ${pref} os ${osDark}`).toBe(bootTheme);
      }
    }
  });

  it("paints the browser chrome in the token page ground for each theme", () => {
    boot({ osDark: false });
    expect(meta()?.toUpperCase()).toBe(semantic.light.bgPage.toUpperCase());
    boot({ osDark: true });
    expect(meta()?.toUpperCase()).toBe(semantic.dark.bgPage.toUpperCase());
  });
});
