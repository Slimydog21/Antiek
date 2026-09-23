/**
 * tokens.contrast.test.ts — every text/background and UI pair the design
 * system offers, in BOTH themes, computed from what renders.
 *
 * WHY IT READS tokens.css AND tailwind.config.js (not tokens.ts): the old
 * version checked token exports on two grounds and passed while the app
 * failed axe 727 times at night, because components consume Tailwind keys
 * (`dark:text-moonlight`, `border-charcoal-1`, `text-emperor`) whose values
 * never met the token file. Here each pair is resolved the way the browser
 * resolves it: the Tailwind key → its CSS var → tokens.css in the given theme
 * (var() chains followed; tokenCss.ts). Change a hex, a Tailwind key or an
 * alias so that a consumed pair drops below WCAG, and this reddens.
 *
 * PROOF IT BITES: point it at another tree and it fails there.
 *   TOKENS_CSS=<path> TAILWIND_CONFIG=<path> npx vitest run src/design/tokens.contrast.test.ts
 * Against origin/main @2c35367ce (pre-semantic layer) 46 of 77 fail,
 * including (first failing ground, measured): dark:text-moonlight 4.08 on the
 * page, dark:border-charcoal-1 1.06, night text-shadow-1 2.90 and
 * text-shadow-2 2.02, night text-emperor 3.78, day text-sun-deep 3.32, day
 * text-aurora 2.05, danger on its own 10% wash 4.05, and the "running"
 * state label 1.26.
 *
 * MATH SOURCE: contrastRatio / over are the shared WCAG helpers in
 * e2e/_ams/visible.ts, the same math the browser experience gates use.
 * No colour literal lives in this file (lint:tokens).
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { contrastRatio, over, relativeLuminance } from "../../e2e/_ams/visible";
import { parseTokensCss, resolveTailwindColor, resolveVar, toRgba, type Rgba, type ThemeName } from "./tokenCss";
import { barAccent, sun, sunLight } from "./tokens";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..");
const cssPath = process.env.TOKENS_CSS ? resolve(process.env.TOKENS_CSS) : join(here, "tokens.css");
const twPath = process.env.TAILWIND_CONFIG ? resolve(process.env.TAILWIND_CONFIG) : join(APP, "tailwind.config.js");
const sheet = parseTokensCss(readFileSync(cssPath, "utf8"));
const twModule = createRequire(import.meta.url)(twPath);
type ColorMap = Record<string, string | Record<string, string>>;
const tw = (twModule.default ?? twModule) as { theme: { extend: Record<string, ColorMap> } };

const AA_TEXT = 4.5; // WCAG 1.4.3
const AA_UI = 3.0; // WCAG 1.4.11
const THEMES: ThemeName[] = ["light", "dark"];

/** A token's colour in a theme. */
function tok(theme: ThemeName, name: string): Rgba {
  const v = resolveVar(sheet, theme, name);
  const c = v === null ? null : toRgba(v);
  if (!c) throw new Error(`${name} does not resolve to a colour in ${theme} (got ${v})`);
  return c;
}

/** What a Tailwind utility renders, e.g. util("dark", "text", "moonlight"). */
function util(theme: ThemeName, kind: "text" | "bg" | "border" | "fill" | "stroke", key: string): Rgba {
  const ext = tw.theme.extend;
  const perUtility =
    { text: ext.textColor, bg: ext.backgroundColor, border: ext.borderColor, fill: ext.fill, stroke: ext.stroke }[kind] ?? {};
  const pick = (v: string | Record<string, string> | undefined) => (typeof v === "object" ? v.DEFAULT : v);
  const value = pick(perUtility[key]) ?? pick(ext.colors[key]);
  const c = value === undefined ? null : resolveTailwindColor(sheet, theme, value);
  if (!c) throw new Error(`${kind}-${key} does not resolve in ${theme} (value ${value})`);
  return c;
}

const ratio = (a: Rgba, b: Rgba) => contrastRatio(a, b.a < 1 ? over(b, { r: 255, g: 255, b: 255 }) : b);
const GROUNDS = ["--bg-page", "--bg-card", "--bg-inset"] as const;

describe("semantic text tokens clear AA 4.5:1 on every ground, both themes", () => {
  const TEXT = ["--text-1", "--text-2", "--text-3", "--sun-ink", "--teal", "--danger", "--success", "--stale", "--not-run"];
  for (const theme of THEMES) {
    for (const fg of TEXT) {
      it(`${theme}: ${fg} on page, card and inset`, () => {
        for (const bg of GROUNDS) {
          expect(ratio(tok(theme, fg), tok(theme, bg)), `${theme} ${fg} on ${bg}`).toBeGreaterThanOrEqual(AA_TEXT);
        }
      });
    }
  }

  it("the text ramp is genuinely stepped: 1 > 2 > 3 on the card in both themes", () => {
    for (const theme of THEMES) {
      const card = tok(theme, "--bg-card");
      const [t1, t2, t3] = ["--text-1", "--text-2", "--text-3"].map((t) => ratio(tok(theme, t), card));
      expect(t1).toBeGreaterThan(t2);
      expect(t2).toBeGreaterThan(t3);
    }
  });
});

describe("UI pairs clear 3:1 (WCAG 1.4.11), both themes", () => {
  for (const theme of THEMES) {
    it(`${theme}: the rule, the focus ring and the keycap edge on every ground`, () => {
      for (const ui of ["--border-rule", "--focus", "--keycap-edge", "--sun-deep"]) {
        for (const bg of GROUNDS) {
          expect(ratio(tok(theme, ui), tok(theme, bg)), `${theme} ${ui} on ${bg}`).toBeGreaterThanOrEqual(AA_UI);
        }
      }
    });

    it(`${theme}: the keycap edge separates from the sun face it frames`, () => {
      expect(ratio(tok(theme, "--keycap-edge"), tok(theme, "--sun"))).toBeGreaterThanOrEqual(AA_UI);
    });
  }

  it("the hairline is decorative (below 3:1 on purpose): boundaries use the rule", () => {
    for (const theme of THEMES) {
      expect(ratio(tok(theme, "--border-hairline"), tok(theme, "--bg-card"))).toBeLessThan(AA_UI);
      expect(ratio(tok(theme, "--border-rule"), tok(theme, "--bg-card"))).toBeGreaterThan(
        ratio(tok(theme, "--border-hairline"), tok(theme, "--bg-card")),
      );
    }
  });
});

describe("fills: what sits on the sun, on a danger fill, on the fixed ink", () => {
  for (const theme of THEMES) {
    it(`${theme}: ink on the sun and its hover/press states`, () => {
      for (const face of ["--sun", "--sun-hover", "--sun-press"]) {
        expect(ratio(tok(theme, "--fixed-ink"), tok(theme, face)), face).toBeGreaterThanOrEqual(AA_TEXT);
        // and what `text-ink` renders (the key must NOT flip to light text at night)
        expect(ratio(util(theme, "text", "ink"), tok(theme, face)), `text-ink on ${face}`).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it(`${theme}: white text on a fill: text-ice-0 and text-ice-1 on bg-emperor and bg-ink`, () => {
      for (const key of ["ice-0", "ice-1"]) {
        expect(ratio(util(theme, "text", key), util(theme, "bg", "emperor")), `text-${key} on bg-emperor`).toBeGreaterThanOrEqual(AA_TEXT);
        expect(ratio(util(theme, "text", key), util(theme, "bg", "ink")), `text-${key} on bg-ink`).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it(`${theme}: the dark islands keep their light text (FloatMenu, the rail)`, () => {
      // bg-ink carries text-bright and muted text-moonlight; the bg-shadow-2
      // field inside it carries text-bright.
      expect(ratio(util(theme, "text", "bright"), util(theme, "bg", "ink"))).toBeGreaterThanOrEqual(AA_TEXT);
      expect(ratio(util(theme, "text", "moonlight"), util(theme, "bg", "ink"))).toBeGreaterThanOrEqual(AA_TEXT);
      expect(ratio(util(theme, "text", "bright"), util(theme, "bg", "shadow-2"))).toBeGreaterThanOrEqual(AA_TEXT);
    });
  }

  for (const theme of THEMES) {
    it(`${theme}: the brand mark keeps paper lobes under ink folds (BrainMark: fill-ice-0 stroke-ink)`, () => {
      // It sits on the dock's sun key and on cards in both themes; the folds
      // are only drawn if the lobes stay paper (UI 3:1, WCAG 1.4.11).
      expect(ratio(util(theme, "stroke", "ink"), util(theme, "fill", "ice-0"))).toBeGreaterThanOrEqual(AA_UI);
      // ice as a pigment is one colour whatever the utility: text, fill, stroke.
      for (const n of [0, 1, 2, 3, 4]) {
        for (const kind of ["fill", "stroke"] as const) {
          expect(util(theme, kind, `ice-${n}`), `${kind}-ice-${n}`).toEqual(util(theme, "text", `ice-${n}`));
        }
      }
    });
  }

  it("the filled success idioms: white on the day green, ink on the night sage", () => {
    expect(ratio(util("light", "text", "ice-0"), util("light", "bg", "success"))).toBeGreaterThanOrEqual(AA_TEXT);
    expect(ratio(util("dark", "text", "ink"), util("dark", "bg", "success"))).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe("composited: washes and the highlighter", () => {
  for (const theme of THEMES) {
    it(`${theme}: danger text on its own 10% and 15% wash (the error banner) stays AA`, () => {
      const danger = util(theme, "text", "danger");
      for (const alpha of [0.1, 0.15]) {
        for (const bg of ["--page", "--card"]) {
          const wash = over({ ...util(theme, "bg", "danger"), a: alpha }, tok(theme, bg));
          expect(contrastRatio(danger, wash), `${theme} text-danger on bg-danger/${alpha * 100} over ${bg}`).toBeGreaterThanOrEqual(AA_TEXT);
        }
      }
    });

    it(`${theme}: text-1 and text-2 stay AA on the hover wash over the card`, () => {
      const hovered = over(tok(theme, "--wash"), tok(theme, "--bg-card"));
      for (const fg of ["--text-1", "--text-2"]) {
        expect(contrastRatio(tok(theme, fg), hovered), `${fg} on wash`).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it(`${theme}: highlighted prose (--mark over page and card) stays AA`, () => {
      for (const bg of ["--bg-page", "--bg-card"]) {
        expect(contrastRatio(tok(theme, "--text-1"), over(tok(theme, "--mark"), tok(theme, bg)))).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });
  }
});

// The two sections below measure against the LEGACY ground names (--page,
// --card, --inset), which exist in every tree: here they alias the semantic
// grounds, and pointed at an older tokens.css (see header) they report the
// real consumed ratios instead of "token missing".
const LEGACY_GROUNDS = ["--page", "--card", "--inset"] as const;

describe("honesty and research states read as text in both themes", () => {
  const STATES = [...sheet.root.keys()].filter((k) => k.startsWith("--state-"));
  it("there is a state family to test", () => {
    expect(STATES.length).toBeGreaterThanOrEqual(5);
  });
  for (const theme of THEMES) {
    for (const s of STATES) {
      it(`${theme}: ${s} is AA text on page and card`, () => {
        for (const bg of ["--page", "--card"]) {
          expect(ratio(tok(theme, s), tok(theme, bg)), `${theme} ${s} on ${bg}`).toBeGreaterThanOrEqual(AA_TEXT);
        }
      });
    }
  }
});

describe("the Tailwind keys call sites actually use, as they render", () => {
  // Base text keys render in both themes (a call site without a dark:
  // override shows the base key at night too); the night keys are used under
  // dark: (dark:text-moonlight ×985 is the largest).
  const TEXT_IN_BOTH = ["ink-soft", "ink-mute", "shadow-1", "shadow-2", "sun-deep", "aurora", "emperor", "danger", "success"];
  const TEXT_AT_NIGHT = ["moonlight", "starlight", "bright", "sun"];

  for (const theme of THEMES) {
    for (const key of TEXT_IN_BOTH) {
      it(`${theme}: text-${key} is AA on page, card and inset`, () => {
        for (const bg of LEGACY_GROUNDS) {
          expect(ratio(util(theme, "text", key), tok(theme, bg)), `${theme} text-${key} on ${bg}`).toBeGreaterThanOrEqual(AA_TEXT);
        }
      });
    }
  }

  for (const key of TEXT_AT_NIGHT) {
    it(`dark:text-${key} is AA on the night page, card and inset`, () => {
      for (const bg of LEGACY_GROUNDS) {
        expect(ratio(util("dark", "text", key), tok("dark", bg)), `dark:text-${key} on ${bg}`).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });
  }

  it("dark: surfaces are the night grounds (dark:bg-charcoal-2 is the card, space-2 the page)", () => {
    const same = (a: Rgba, b: Rgba) => a.r === b.r && a.g === b.g && a.b === b.b;
    expect(same(util("dark", "bg", "charcoal-2"), tok("dark", "--card"))).toBe(true);
    expect(same(util("dark", "bg", "space-2"), tok("dark", "--page"))).toBe(true);
  });

  for (const theme of THEMES) {
    it(`${theme}: border-rule and the DEFAULT border mark boundaries at 3:1`, () => {
      for (const bg of LEGACY_GROUNDS) {
        expect(ratio(util(theme, "border", "rule"), tok(theme, bg)), `${theme} border-rule on ${bg}`).toBeGreaterThanOrEqual(AA_UI);
        expect(ratio(util(theme, "border", "DEFAULT"), tok(theme, bg)), `${theme} border on ${bg}`).toBeGreaterThanOrEqual(AA_UI);
      }
    });
  }

  it("dark:border-charcoal-1 (×442 night boundaries) reaches 3:1 on the night grounds", () => {
    for (const bg of LEGACY_GROUNDS) {
      expect(ratio(util("dark", "border", "charcoal-1"), tok("dark", bg)), `dark:border-charcoal-1 on ${bg}`).toBeGreaterThanOrEqual(AA_UI);
    }
  });
});

describe("AMS-SPR-09 brand invariants (kept)", () => {
  const hex = (h: string) => toRgba(h)!;
  const chroma = (c: Rgba) => (Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b)) / 255;

  it("the bottom-tab yellow stays the brand lemon by day and a loud glow by night", () => {
    expect(barAccent.day).toBe(sun.base);
    expect(barAccent.night).not.toBe(sun.glow.night);
    expect(chroma(hex(barAccent.night))).toBeGreaterThan(0.6);
    expect(chroma(hex(barAccent.day))).toBeGreaterThan(chroma(hex(sun.glow.day)));
    expect(chroma(hex(sunLight.base))).toBeLessThan(chroma(hex(sun.base)));
  });

  it("the sun is a fill, never text on paper (the reason --sun-ink exists)", () => {
    expect(ratio(tok("light", "--sun"), tok("light", "--page"))).toBeLessThan(AA_UI);
    expect(ratio(tok("light", "--sun-ink"), tok("light", "--page"))).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it("reuses the visible.ts WCAG math (white = 1, black = 0)", () => {
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 5);
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeCloseTo(0, 5);
  });
});
