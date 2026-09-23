/**
 * The shipped faces swap in without re-wrapping lines.
 *
 * Inter and JetBrains Mono load with font-display: swap. Until the woff2
 * arrives, text sets in whatever the stack names next; with plain system-ui
 * (14% narrower than Inter on UI copy) the swap re-wrapped ledes and grew
 * cards. Each shipped face therefore has a metric-matched local fallback
 * (size-adjust plus ascent/descent/line-gap overrides, index.css) and every
 * stack names it second: tokens.css, tokens.ts and the Tailwind fontFamily.
 *
 * The numbers are measurements, not guesses; this test pins that they exist
 * and are wired. The reflow they remove was measured in Chromium over five
 * routes at 1280 and 390 (fonts blocked vs loaded): 15 text boxes changing
 * height by 86 px in total before, 1 box by 23 px after.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { type } from "./tokens";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..");
const indexCss = readFileSync(join(APP, "src", "index.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const tokensCss = readFileSync(join(here, "tokens.css"), "utf8");
const twModule = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));
const tw = (twModule.default ?? twModule) as { theme: { extend: { fontFamily: Record<string, string[]> } } };

const faces = [...indexCss.matchAll(/@font-face\s*{([^}]*)}/g)].map((m) => ({
  family: m[1].match(/font-family:\s*"([^"]+)"/)?.[1] ?? "",
  body: m[1],
}));
const unquote = (s: string) => s.trim().replace(/^["']|["']$/g, "");
const stack = (s: string) => s.split(",").map(unquote);

const SHIPPED = faces.filter((f) => /url\(/.test(f.body)).map((f) => f.family);

describe("font fallbacks: the swap does not re-wrap", () => {
  it("the shipped faces are the two the tokens name", () => {
    expect(SHIPPED.sort()).toEqual(["Inter", "JetBrains Mono"]);
  });

  for (const family of ["Inter", "JetBrains Mono"]) {
    const fallback = `${family} Fallback`;

    it(`${family}: a local, metric-matched "${fallback}" face exists`, () => {
      const face = faces.find((f) => f.family === fallback);
      expect(face, `@font-face "${fallback}" in index.css`).toBeDefined();
      expect(face!.body).toMatch(/src:\s*local\(/);
      for (const d of ["size-adjust", "ascent-override", "descent-override", "line-gap-override"]) {
        expect(face!.body, d).toMatch(new RegExp(`${d}:\\s*\\d+(\\.\\d+)?%`));
      }
    });

    it(`${family}: every stack names "${fallback}" right after it`, () => {
      const key = family === "Inter" ? "sans" : "mono";
      const cssStack = tokensCss.match(new RegExp(`--${key}:\\s*([^;]+);`))?.[1] ?? "";
      for (const [where, s] of [
        ["tokens.css", stack(cssStack)],
        ["tokens.ts", stack(type[key])],
        ["tailwind fontFamily", tw.theme.extend.fontFamily[key].map(unquote)],
      ] as const) {
        expect(s.slice(0, 2), where).toEqual([family, fallback]);
      }
    });
  }
});
