/**
 * controls.contrast.test.ts — the colour pairs the Lemon controls actually
 * render, resolved from their class strings through tailwind.config.js and
 * tokens.css in BOTH themes (the same resolution tokens.contrast.test.ts uses).
 *
 * The audit measured the old pairs in Chromium: the toast dismiss ✕ at 1.08:1
 * on the night info toast (text-ink/60), 2.13 on the day ok toast; the field
 * and overlay edge (border-sun) at 1.29:1 on the day page. Point a class back
 * at one of those and this reddens.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { contrastRatio } from "../../../e2e/_ams/visible";
import { parseTokensCss, resolveTailwindColor, resolveVar, toRgba, type Rgba, type ThemeName } from "../../design/tokenCss";
import { base as buttonBase, variants as buttonVariants } from "./LemonButton";
import { kindStyles as toastKinds } from "./LemonToast";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const sheet = parseTokensCss(readFileSync(join(APP, "src", "design", "tokens.css"), "utf8"));
const twModule = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));
type ColorMap = Record<string, string | Record<string, string>>;
const ext = ((twModule.default ?? twModule) as { theme: { extend: Record<string, ColorMap> } }).theme.extend;
const THEMES: ThemeName[] = ["light", "dark"];
const AA_TEXT = 4.5;
const AA_UI = 3;

type Kind = "text" | "bg" | "border";
/** What a colour utility renders to: `text-ink`, `bg-card`, `border-rule`. */
function util(theme: ThemeName, kind: Kind, key: string): Rgba {
  const per = { text: ext.textColor, bg: ext.backgroundColor, border: ext.borderColor }[kind] ?? {};
  const pick = (v: string | Record<string, string> | undefined) => (typeof v === "object" ? v.DEFAULT : v);
  const value = pick(per[key]) ?? pick(ext.colors[key]);
  const c = value === undefined ? null : resolveTailwindColor(sheet, theme, value);
  if (!c) throw new Error(`${kind}-${key} does not resolve in ${theme}`);
  return c;
}
function tok(theme: ThemeName, name: string): Rgba {
  const v = resolveVar(sheet, theme, name);
  const c = v === null ? null : toRgba(v);
  if (!c) throw new Error(`${name} does not resolve in ${theme}`);
  return c;
}
/** The class a theme applies for a utility kind: `dark:` wins at night. */
function classFor(classes: string, theme: ThemeName, kind: Kind, variant = ""): string | null {
  const tokens = classes.split(/\s+/);
  const re = new RegExp(`^${variant}${kind}-([a-z0-9-]+)$`);
  const plain = tokens.map((t) => t.match(re)?.[1]).filter((k): k is string => !!k && !/^(xs|sm|base|lg|xl|left|right|center|current|transparent)$/.test(k));
  const dark = tokens.map((t) => t.match(new RegExp(`^dark:${variant}${kind}-([a-z0-9-]+)$`))?.[1]).filter(Boolean) as string[];
  return (theme === "dark" && dark.length ? dark.at(-1) : plain.at(-1)) ?? null;
}
const ratio = (a: Rgba, b: Rgba) => contrastRatio(a, b);

describe("toasts: every kind's text (and so its icon and dismiss ✕) reads, both themes", () => {
  for (const theme of THEMES) {
    for (const [kind, classes] of Object.entries(toastKinds)) {
      it(`${theme} ${kind}: text on the toast face >= 4.5:1`, () => {
        const fg = util(theme, "text", classFor(classes, theme, "text")!);
        const bg = util(theme, "bg", classFor(classes, theme, "bg")!);
        expect(ratio(fg, bg), `${theme} ${kind}`).toBeGreaterThanOrEqual(AA_TEXT);
      });
    }
  }
  it("the dismiss control inherits the text colour instead of a faded ink", () => {
    const src = readFileSync(join(here, "LemonToast.tsx"), "utf8");
    const dismiss = src.slice(src.indexOf('aria-label="Dismiss"'), src.indexOf('aria-label="Dismiss"') + 400);
    expect(dismiss).toMatch(/text-current/);
    expect(dismiss).not.toMatch(/text-ink\/\d+/);
  });
});

describe("buttons: every variant's label reads on its face, both themes", () => {
  const GROUNDS = ["--bg-page", "--bg-card", "--bg-inset"];
  for (const theme of THEMES) {
    for (const [variant, classes] of Object.entries(buttonVariants)) {
      it(`${theme} ${variant}: label >= 4.5:1`, () => {
        const fg = util(theme, "text", classFor(classes, theme, "text")!);
        const face = classFor(classes, theme, "bg");
        if (face === "transparent" || face === null) {
          for (const g of GROUNDS) expect(ratio(fg, tok(theme, g)), `${theme} ${variant} on ${g}`).toBeGreaterThanOrEqual(AA_TEXT);
        } else {
          expect(ratio(fg, util(theme, "bg", face)), `${theme} ${variant}`).toBeGreaterThanOrEqual(AA_TEXT);
        }
      });
    }
    it(`${theme}: the designed disabled pair (text-3 on inset) still reads`, () => {
      const fg = util(theme, "text", classFor(buttonBase, theme, "text", "aria-disabled:")!);
      const bg = util(theme, "bg", classFor(buttonBase, theme, "bg", "aria-disabled:")!);
      expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_TEXT);
    });
    it(`${theme}: the primary key's edge frames the sun face and the page >= 3:1`, () => {
      const edge = util(theme, "border", classFor(buttonVariants.primary, theme, "border")!);
      expect(ratio(edge, tok(theme, "--sun"))).toBeGreaterThanOrEqual(AA_UI);
      expect(ratio(edge, tok(theme, "--bg-page"))).toBeGreaterThanOrEqual(AA_UI);
    });
  }
});

describe("fields and islands: the edge is a boundary you can see (WCAG 1.4.11)", () => {
  const FILES = ["LemonInput.tsx", "LemonTextarea.tsx", "LemonSelect.tsx", "LemonModal.tsx", "LemonDropdown.tsx", "LemonCard.tsx"];
  it("no field or overlay edge is drawn in the sun (1.29:1 on the day page)", () => {
    for (const f of FILES) {
      expect(readFileSync(join(here, f), "utf8"), f).not.toMatch(/\bborder-sun\b/);
    }
  });
  for (const theme of THEMES) {
    it(`${theme}: border-rule clears 3:1 on the page and on the card`, () => {
      const rule = util(theme, "border", "rule");
      expect(ratio(rule, tok(theme, "--bg-page"))).toBeGreaterThanOrEqual(AA_UI);
      expect(ratio(rule, tok(theme, "--bg-card"))).toBeGreaterThanOrEqual(AA_UI);
    });
  }
});

describe("the tip and the focus ring", () => {
  for (const theme of THEMES) {
    it(`${theme}: the tip (page colour on text-1) reads >= 4.5:1`, () => {
      const css = readFileSync(join(here, "..", "Tooltip.css"), "utf8");
      expect(css).toMatch(/background:\s*var\(--text-1\)/);
      expect(css).toMatch(/color:\s*var\(--bg-page\)/);
      expect(ratio(tok(theme, "--bg-page"), tok(theme, "--text-1"))).toBeGreaterThanOrEqual(AA_TEXT);
    });
    it(`${theme}: the focus ring (--focus) clears 3:1 on page, card and inset`, () => {
      for (const g of ["--bg-page", "--bg-card", "--bg-inset"]) {
        expect(ratio(util(theme, "border", "focus"), tok(theme, g)), `${theme} ${g}`).toBeGreaterThanOrEqual(AA_UI);
      }
    });
  }
});
