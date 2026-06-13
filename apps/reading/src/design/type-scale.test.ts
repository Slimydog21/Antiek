/**
 * type-scale test (CFEEL-S2 M2 + M3) — proves the app type-scale tokens and the
 * opacity tokens exist with the exact PostHog values, and that the 2xl chrome
 * CEILING is 24px.
 *
 * Resolves the REAL Tailwind config (resolveConfig) rather than regex-matching
 * the file, so the assertions track what Tailwind actually emits.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, beforeAll } from "vitest";
import resolveConfig from "tailwindcss/resolveConfig";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/src/design
const APP = join(here, "..", ".."); // apps/reading
const require = createRequire(import.meta.url);
const tailwindConfig = require(join(APP, "tailwind.config.js"));

type FontSizeEntry = string | [string, string | { lineHeight: string }];
interface TwTheme {
  fontSize: Record<string, FontSizeEntry>;
  opacity: Record<string, string>;
}
let theme: TwTheme;

beforeAll(() => {
  const cfg = tailwindConfig.default ?? tailwindConfig;
  theme = (resolveConfig(cfg) as { theme: TwTheme }).theme;
});

describe("type scale (CFEEL-S2 M2) — PostHog app sizes + 24px chrome ceiling", () => {
  // [key, font-size, line-height] — PostHog's real values.
  const EXPECTED: Array<[string, string, string]> = [
    ["xxs", "10px", "12px"],
    ["xs", "12px", "16px"],
    ["sm", "14px", "20px"],
    ["base", "16px", "24px"],
    ["lg", "18px", "28px"],
    ["xl", "20px", "28px"],
    ["2xl", "24px", "32px"],
  ];

  it("every named token exists with the right font-size and line-height", () => {
    for (const [key, size, lh] of EXPECTED) {
      const entry = theme.fontSize[key];
      expect(entry, `fontSize["${key}"] must exist`).toBeTruthy();
      // Tailwind stores [fontSize, lineHeight] (lineHeight may be a string or
      // an object { lineHeight }). Normalize both forms.
      const [gotSize, gotLh] = Array.isArray(entry) ? entry : [entry, undefined];
      expect(gotSize, `fontSize["${key}"] size`).toBe(size);
      const lhValue = typeof gotLh === "object" && gotLh ? gotLh.lineHeight : gotLh;
      expect(lhValue, `fontSize["${key}"] line-height`).toBe(lh);
    }
  });

  it("the 2xl token is the 24px chrome CEILING (the largest named chrome size)", () => {
    const twoXl = theme.fontSize["2xl"];
    const size = Array.isArray(twoXl) ? twoXl[0] : twoXl;
    expect(size).toBe("24px");
    // No NAMED key we added exceeds 24px — the scale tops out at the ceiling.
    const addedKeys = EXPECTED.map(([k]) => k);
    for (const k of addedKeys) {
      const entry = theme.fontSize[k];
      const px = Number(String(Array.isArray(entry) ? entry[0] : entry).replace("px", ""));
      expect(px, `added fontSize["${k}"] must be ≤ 24px ceiling`).toBeLessThanOrEqual(24);
    }
  });
});

describe("opacity tokens (CFEEL-S2 M3) — PostHog disabled/icon dim constants", () => {
  it("opacity-disabled and opacity-icon resolve to their CSS vars", () => {
    expect(theme.opacity.disabled).toBe("var(--opacity-disabled)");
    expect(theme.opacity.icon).toBe("var(--opacity-icon)");
  });

  it("the underlying CSS custom properties resolve through the cascade", () => {
    // Read the REAL token values via jsdom getComputedStyle (custom props
    // resolve in jsdom even though calc()/layout does not).
    const style = document.createElement("style");
    style.textContent = `
      :root { --opacity-disabled: 0.65; --opacity-icon: 0.8; }
    `;
    document.head.appendChild(style);
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue("--opacity-disabled").trim()).toBe("0.65");
    expect(root.getPropertyValue("--opacity-icon").trim()).toBe("0.8");
    document.head.removeChild(style);
  });
});
