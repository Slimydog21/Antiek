/**
 * tokens.contrast.test.ts — the AMS-SPR-09 AA backstop for the weathered
 * "light" re-tone (milestone M4).
 *
 * WHAT IT GUARANTEES
 * ------------------
 * SPR-09 dialled the loud lemon back to a softer, weathered light across the
 * VAR-DRIVEN accent/highlight roles (`sun.deep`, `sun.glow`, `sun.highlight.*`
 * + the new `sunLight` family) while keeping the bottom-tab yellow LOUD
 * (`sun.base` / `barAccent`). Because those token VALUES feed real consumed
 * pairs, this test reads the ACTUAL token exports and asserts every consumed
 * pair still clears WCAG:
 *
 *   (1) Highlighter text ≥ 4.5:1 (WCAG AA 1.4.3). The operator's highlighter
 *       (`src/index.css ::selection`) paints `--sun-hl-{faint,day,night}` as a
 *       translucent veil OVER the prose surface; the prose text (`ink`) reads
 *       over [veil composited over surface]. That composited contrast must
 *       clear 4.5:1, day and night, on the real consumed surfaces.
 *   (2) Accent-edge ≥ 3:1 (WCAG 1.4.11 non-text contrast). The re-toned
 *       `sun.deep` is the depth/hover edge (day) and the night offset-shadow
 *       glow (`shadow.night` reads `var(--sun-deep)`); as a meaningful edge it
 *       must clear 3:1 against the surfaces it sits on. The new `sunLight.deep`
 *       (== `sun.deep.day`) carries the same floor.
 *   (3) `barAccent` still carries the BRAND CHROMA — day is the unchanged
 *       brand lemon (`sun.base`), night the loud warm glow; neither softened
 *       with the chrome. We assert the values AND that the bar's chroma is
 *       strictly LOUDER than the softened chrome glow (the "keep the tab loud"
 *       invariant, not just "unchanged string").
 *
 * MATH SOURCE (rigor #4 — reuse, don't duplicate). `contrastRatio` /
 * `relativeLuminance` are the EXISTING pure WCAG helpers in
 * `e2e/_ams/visible.ts` (L260 / L251) — the same math the browser
 * experience-gate (`assertContrast`) uses. We IMPORT them here (verified to
 * load under the jsdom vitest) so the unit floor and the browser gate compute
 * contrast identically; there is one formula, not two. `over()` is the
 * straight-alpha source-over composite, also from visible.ts.
 *
 * This is the durable proof a future re-tune cannot silently drop a consumed
 * pair below AA: change a hex in tokens.ts, and if it breaks a real pair this
 * reddens. The browser gate (e2e/token-retone.spec.ts) proves the same facts
 * on live rendered pixels.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { contrastRatio, over, relativeLuminance, type Rgb, type Rgba } from "../../e2e/_ams/visible";

import { barAccent, shadow, sun, sunLight, surface } from "./tokens";

// ── colour parsing (local, tiny; visible.ts's parseRgba is rgb()-string only) ──
// NOTE: this file holds ZERO raw hex literals — every colour is read FROM the
// token exports (sun*, barAccent, surface ramp). That keeps token-lint's "no
// new hex outside the token files" invariant pristine AND makes the test the
// real source-of-truth consumer (a future re-tune that breaks a pair reddens
// here without anyone hand-syncing a hardcoded surface value).

/** Parse a #RRGGBB hex literal (sourced from a token export) into {r,g,b}. */
function hex(h: string): Rgb {
  const s = h.replace("#", "");
  return {
    r: parseInt(s.slice(0, 2), 16),
    g: parseInt(s.slice(2, 4), 16),
    b: parseInt(s.slice(4, 6), 16),
  };
}

/** Parse a `rgba(r,g,b,a)` token literal into {r,g,b,a}. */
function rgba(s: string): Rgba {
  const m = s.match(/rgba?\(([^)]+)\)/);
  const p = (m?.[1] ?? "0,0,0,1").split(",").map((x) => parseFloat(x.trim()));
  return { r: p[0] ?? 0, g: p[1] ?? 0, b: p[2] ?? 0, a: p[3] ?? 1 };
}

/** Rough chroma (max−min channel, 0…1) — a loudness proxy for "weathered vs loud". */
function chroma(c: Rgb): number {
  return (Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b)) / 255;
}

// ── the real consumed surfaces + prose text, READ FROM the surface ramp ──
// (tokens.ts `surface`: day [0]=ice-0/card, [2]=ice-2/page, [9]=ink; night
//  [2]=space-2/page, [4]=charcoal-2/card, [9]=bright/ink). Sourcing these from
//  the export — not a hardcoded hex — means the test tracks the surfaces a
//  re-tune actually lands on, and holds no literal of its own.
const ICE_0 = hex(surface.day[0]); // card face
const ICE_2 = hex(surface.day[2]); // page background
const INK_DAY = hex(surface.day[9]); // day prose text (--ink)
const CARD_NIGHT = hex(surface.night[4]); // charcoal-2 card
const PAGE_NIGHT = hex(surface.night[2]); // space-2 page
const INK_NIGHT = hex(surface.night[9]); // night prose text (--ink / bright)

const AA_TEXT = 4.5; // WCAG 1.4.3 (text over its background)
const AA_NONTEXT = 3.0; // WCAG 1.4.11 (non-text / UI-edge contrast)

// ── CSS-custom-property resolver (for the badge AA gate, ALC SPR-08 M2) ───────
// The SceneStatusBadge consumes `--badge-text` over `--badge-bg`, both defined
// ONLY in tokens.css (the night `--badge-text` has no named TS mirror — it is
// `--shadow-2`'s night override). To make the badge AA floor a REAL gate
// (not a comment), we read the badge pair STRAIGHT FROM tokens.css — the exact
// source the badge renders against — and resolve its `var()` chain per theme.
// Day = the top `:root { … }` block; night = the `@media (prefers-color-scheme:
// dark) :root { … }` block (the only two theme scopes — theme is driven purely
// by prefers-color-scheme, verified in index.css). A future edit that reverts
// `--badge-text` to a translucent/lower-contrast value reddens HERE.
const TOKENS_CSS = readFileSync(resolve(import.meta.dirname, "./tokens.css"), "utf8");

/** Slice the body of the FIRST `:root { … }` at/after `fromIndex` (brace-matched). */
function rootBlockBody(css: string, fromIndex: number): string {
  const rootAt = css.indexOf(":root", fromIndex);
  const open = css.indexOf("{", rootAt);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") {
      depth--;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error("tokens.css: unbalanced :root block");
}

const DAY_BLOCK = rootBlockBody(TOKENS_CSS, 0);
const NIGHT_BLOCK = rootBlockBody(TOKENS_CSS, TOKENS_CSS.indexOf("prefers-color-scheme: dark"));

/** Read the LAST declaration of `--name` in a block body (later wins, like CSS). */
function declValue(blockBody: string, name: string): string {
  const re = new RegExp(`--${name}\\s*:\\s*([^;]+);`, "g");
  let last: string | undefined;
  for (const m of blockBody.matchAll(re)) last = m[1].trim();
  if (last === undefined) throw new Error(`tokens.css: --${name} not declared in block`);
  return last;
}

/**
 * Resolve a CSS custom property to a concrete colour, following `var(--x)`
 * chains within the theme block (night falls back to day for vars it doesn't
 * override — real CSS cascade). Returns a `#RRGGBB` hex (the badge tokens all
 * resolve to a solid hex).
 */
function resolveVar(name: string, nightBlock: string | null): string {
  const seen = new Set<string>();
  const step = (n: string): string => {
    if (seen.has(n)) throw new Error(`tokens.css: var cycle at --${n}`);
    seen.add(n);
    // Night overrides win; otherwise fall back to the day :root declaration.
    let raw: string;
    if (nightBlock && new RegExp(`--${n}\\s*:`).test(nightBlock)) raw = declValue(nightBlock, n);
    else raw = declValue(DAY_BLOCK, n);
    const m = raw.match(/^var\(\s*--([\w-]+)\s*\)$/);
    return m ? step(m[1]) : raw;
  };
  return step(name);
}

/** Contrast of prose `text` over a translucent `veil` composited on `surface`. */
function highlighterContrast(veil: string, surface: Rgb, text: Rgb): number {
  return contrastRatio(text, over(rgba(veil), surface));
}

describe("AMS-SPR-09 token re-tone — every consumed pair still clears WCAG", () => {
  // ── M2: the bottom-tab / brand stays LOUD (unchanged) ─────────────────────
  describe("M2 — the bottom-tab yellow + brand constant stay LOUD", () => {
    // The brand lemon, sourced from the export (no literal): the byte the
    // bottom tab + Werner mark carry and SPR-09 must NOT soften.
    const BRAND_LEMON = sun.base; // the loud brand lemon (no literal here)

    it("barAccent day = the brand lemon (sun.base), unchanged", () => {
      expect(barAccent.day).toBe(BRAND_LEMON);
    });

    it("barAccent night is LOUD and decoupled from the softened glow", () => {
      // The decoupling the re-tone required: the night bar must NOT track the
      // now-softened sun.glow.night — it is pinned to its own loud glow.
      expect(barAccent.night).not.toBe(sun.glow.night);
      // And it is genuinely loud: high chroma, far above the weathered chrome.
      expect(chroma(hex(barAccent.night))).toBeGreaterThan(0.6);
    });

    it("the bar carries MORE chroma than the softened chrome glow (loud vs weathered)", () => {
      // Not just "string unchanged": the bar must read strictly louder than the
      // re-toned chrome accents — the substance of "keep the tab loud".
      expect(chroma(hex(barAccent.day))).toBeGreaterThan(chroma(hex(sun.glow.day)));
      expect(chroma(hex(barAccent.night))).toBeGreaterThan(chroma(hex(sun.glow.night)));
      // And the weathered light family is genuinely lower-chroma than the brand.
      expect(chroma(hex(sunLight.base))).toBeLessThan(chroma(hex(sun.base)));
    });
  });

  // ── M4(1): highlighter text ≥ 4.5:1, day + night, on the real surfaces ────
  describe("M1.4.3 — highlighter text clears AA 4.5:1 over [veil over surface]", () => {
    it("day faint/full veils keep ink ≥ 4.5:1 on card (ice-0) and page (ice-2)", () => {
      for (const veil of [sun.highlight.faint, sun.highlight.day]) {
        for (const surface of [ICE_0, ICE_2]) {
          expect(highlighterContrast(veil, surface, INK_DAY)).toBeGreaterThanOrEqual(AA_TEXT);
        }
      }
    });

    it("night veil keeps night ink ≥ 4.5:1 on card and page", () => {
      for (const surface of [CARD_NIGHT, PAGE_NIGHT]) {
        expect(highlighterContrast(sun.highlight.night, surface, INK_NIGHT)).toBeGreaterThanOrEqual(
          AA_TEXT,
        );
      }
    });
  });

  // ── M4(2): accent-edge ≥ 3:1 per WCAG 1.4.11 ──────────────────────────────
  describe("M1.4.11 — the re-toned accent edge (sun.deep / sunLight.deep) clears 3:1", () => {
    it("day sun.deep clears 3:1 on card (ice-0) and page (ice-2)", () => {
      for (const surface of [ICE_0, ICE_2]) {
        expect(contrastRatio(hex(sun.deep.day), surface)).toBeGreaterThanOrEqual(AA_NONTEXT);
      }
    });

    it("night sun.deep — the offset-shadow glow — clears 3:1 on card and page", () => {
      for (const surface of [CARD_NIGHT, PAGE_NIGHT]) {
        expect(contrastRatio(hex(sun.deep.night), surface)).toBeGreaterThanOrEqual(AA_NONTEXT);
      }
    });

    it("sunLight.deep (the named weathered edge) clears 3:1 on day surfaces", () => {
      for (const surface of [ICE_0, ICE_2]) {
        expect(contrastRatio(hex(sunLight.deep), surface)).toBeGreaterThanOrEqual(AA_NONTEXT);
      }
    });
  });

  // ── Sibling-derivation sanity: the re-toned tokens are internally consistent ──
  describe("internal consistency of the weathered family", () => {
    it("sunLight.deep equals sun.deep.day (one weathered ochre, two names)", () => {
      expect(sunLight.deep).toBe(sun.deep.day);
    });

    it("the night offset shadows glow with the re-toned sun.deep.night", () => {
      // tokens.css night --shadow-z* read var(--sun-deep); the TS sibling must
      // bake the SAME re-toned night depth hex.
      expect(shadow.night.z1).toContain(sun.deep.night.replace("#", ""));
    });

    it("the highlighter veils are built from the weathered family rgb", () => {
      // faint/day veils are built from sunLight.base's rgb.
      const light = hex(sunLight.base);
      for (const veil of [sun.highlight.faint, sun.highlight.day]) {
        const v = rgba(veil);
        expect([v.r, v.g, v.b]).toEqual([light.r, light.g, light.b]);
      }
      // night veil is built from sun.glow.night's rgb.
      const glowN = hex(sun.glow.night);
      const vn = rgba(sun.highlight.night);
      expect([vn.r, vn.g, vn.b]).toEqual([glowN.r, glowN.g, glowN.b]);
    });
  });

  // ── M2 (ALC SPR-08, closes SPR-05→SPR-08 deferral a): the operator badge ──
  // The SceneStatusBadge AA fix was previously asserted only structurally
  // (SceneStatusBadge.test.tsx checks it consumes --badge-bg/--badge-text). This
  // is the NUMERIC gate it deferred to: --badge-text over --badge-bg must clear
  // AA-normal (4.5:1) on BOTH themes, read from tokens.css (the real source). A
  // token edit that drops the badge below AA reddens here — the hollow gate is
  // now a real one.
  describe("M2 — the operator badge text clears AA over its opaque chip, both themes", () => {
    it("day --badge-text over --badge-bg ≥ 4.5:1", () => {
      const text = hex(resolveVar("badge-text", null));
      const bg = hex(resolveVar("badge-bg", null));
      // The recorded day pair (shadow-1 over glass-bg-solid) is 6.38:1.
      expect(contrastRatio(text, bg)).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it("night --badge-text over --badge-bg ≥ 4.5:1", () => {
      const text = hex(resolveVar("badge-text", NIGHT_BLOCK));
      const bg = hex(resolveVar("badge-bg", NIGHT_BLOCK));
      // The recorded night pair (night shadow-2 over night glass-bg-solid) is 6.95:1.
      expect(contrastRatio(text, bg)).toBeGreaterThanOrEqual(AA_TEXT);
    });
  });

  // A guard so relativeLuminance is exercised (and the import can't be dropped
  // as "unused" by a future refactor) — white is full luminance, black is zero.
  it("reuses the visible.ts WCAG math (relativeLuminance white=1, black=0)", () => {
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 5);
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeCloseTo(0, 5);
  });
});
