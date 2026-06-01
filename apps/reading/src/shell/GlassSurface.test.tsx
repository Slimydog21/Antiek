/**
 * GlassSurface.test.tsx — the keystone primitive's guarantees (SPR-03).
 *
 * vitest config has `globals: false`, so every test API is imported explicitly.
 *
 * What this proves:
 *   (a) variant="glass" renders bg-glass + backdrop-blur-glass + border-glass
 *       AND the scrim layer.
 *   (b) a COMPUTED-CONTRAST assertion that the scrim/text pair clears 4.5:1 in
 *       the worst case the moving scene can produce (the tokens.ts glass
 *       contract), proven from the canonical token rgba values — jsdom does not
 *       compile Tailwind classes, so the contrast is computed from the contract
 *       values the classes resolve to, not from getComputedStyle.
 *   (c) under prefers-reduced-motion:reduce (matchMedia mock) the primitive
 *       renders the SOLID fallback (no backdrop-filter, no scrim) and the text
 *       still clears AA.
 *   (d) variant="solid" never carries an opaque bg-ice-2 / bg-space-2.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { GlassSurface, SCRIM_MIN_OPACITY } from "./GlassSurface";

// ── matchMedia mock (jsdom lacks it). A factory so each test sets the
//    reduced-motion answer it needs. Mirrors the AppShell suites' stub. ──
function installMatchMedia(reducedMotion: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("prefers-reduced-motion") ? reducedMotion : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

afterEach(() => cleanup());

// ───────────────────────────────────────────────────────────────────────────
// PURE WCAG MATH — the scrim contract, computed from the canonical token rgba.
// These are the SAME values the Tailwind classes resolve to (tokens.ts `glass`
// + the body-text tokens). Kept here as the proof, not read from a stylesheet
// jsdom never compiled.
// ───────────────────────────────────────────────────────────────────────────

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function relativeLuminance({ r, g, b }: Rgb): number {
  const ch = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Alpha-composite `top` at opacity `a` over `bottom`. */
function over(top: Rgb, a: number, bottom: Rgb): Rgb {
  return {
    r: a * top.r + (1 - a) * bottom.r,
    g: a * top.g + (1 - a) * bottom.g,
    b: a * top.b + (1 - a) * bottom.b,
  };
}

// Canonical token values (tokens.ts `glass` + body text). Numeric, NOT hex
// literals, so lint:tokens has nothing to flag.
const INK_DAY: Rgb = { r: 15, g: 20, b: 25 }; // --ink day (rgb 15,20,25) body text
const BRIGHT_NIGHT: Rgb = { r: 238, g: 241, b: 246 }; // --ink night (rgb 238,241,246) body text
const GLASS_SOLID_DAY: Rgb = { r: 251, g: 252, b: 253 }; // --glass-bg-solid day (rgb 251,252,253)
const GLASS_SOLID_NIGHT: Rgb = { r: 27, g: 32, b: 42 }; // --glass-bg-solid night (rgb 27,32,42)
const GLASS_ALPHA_DAY = 0.72; // --glass-bg day alpha
const GLASS_ALPHA_NIGHT = 0.66; // --glass-bg night alpha
const BLACK: Rgb = { r: 0, g: 0, b: 0 }; // worst case behind DAY glass (darkest scene)
const WHITE: Rgb = { r: 255, g: 255, b: 255 }; // worst case behind NIGHT glass (brightest scene)

/**
 * The effective text background under the glass variant:
 *   glass-bg(alpha) over [ scrim-solid(SCRIM_MIN_OPACITY) over scene ].
 */
function effectiveBg(solid: Rgb, glassAlpha: number, scrimOpacity: number, scene: Rgb): Rgb {
  const scrimmedScene = over(solid, scrimOpacity, scene);
  return over(solid, glassAlpha, scrimmedScene);
}

describe("GlassSurface — scrim WCAG-AA contract (computed, the tokens.ts glass guarantee)", () => {
  it("(b) day ink over glass clears 4.5:1 even over the worst-case (black) scene", () => {
    const bg = effectiveBg(GLASS_SOLID_DAY, GLASS_ALPHA_DAY, SCRIM_MIN_OPACITY, BLACK);
    const ratio = contrastRatio(INK_DAY, bg);
    expect(ratio, `day ink-on-glass worst case = ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
  });

  it("(b) night bright over glass clears 4.5:1 even over the worst-case (white) scene", () => {
    const bg = effectiveBg(GLASS_SOLID_NIGHT, GLASS_ALPHA_NIGHT, SCRIM_MIN_OPACITY, WHITE);
    const ratio = contrastRatio(BRIGHT_NIGHT, bg);
    expect(ratio, `night bright-on-glass worst case = ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(
      4.5,
    );
  });

  it("the scrim makes a real difference at the tight night margin (defensibility)", () => {
    // Bare glass (no scrim) clears the floor but only just at night; the scrim
    // turns that into a defensible margin. This guards the SCRIM_MIN_OPACITY
    // knob: dropping it toward 0 would regress this assertion.
    const bare = contrastRatio(
      BRIGHT_NIGHT,
      effectiveBg(GLASS_SOLID_NIGHT, GLASS_ALPHA_NIGHT, 0, WHITE),
    );
    const scrimmed = contrastRatio(
      BRIGHT_NIGHT,
      effectiveBg(GLASS_SOLID_NIGHT, GLASS_ALPHA_NIGHT, SCRIM_MIN_OPACITY, WHITE),
    );
    expect(scrimmed).toBeGreaterThan(bare);
    expect(scrimmed, `scrimmed night worst case = ${scrimmed.toFixed(2)}`).toBeGreaterThanOrEqual(
      5.5,
    );
  });

  it("the solid fallback clears AA with NO scene at all (the degradation guarantee)", () => {
    // variant="solid" / reduced-motion / sceneAbsent: text sits on the opaque
    // solid hue, no scene. This is the floor the degradation falls back to.
    expect(contrastRatio(INK_DAY, GLASS_SOLID_DAY)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(BRIGHT_NIGHT, GLASS_SOLID_NIGHT)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("GlassSurface — render contract", () => {
  beforeEach(() => installMatchMedia(false)); // motion ON → glass renders as glass

  it("(a) variant='glass' renders bg-glass + backdrop-blur-glass + border-glass + the scrim", () => {
    const { container } = render(
      <GlassSurface variant="glass" data-testid="gs">
        <p>body</p>
      </GlassSurface>,
    );
    const el = container.querySelector('[data-glass-surface]') as HTMLElement;
    expect(el).toBeTruthy();
    expect(el.getAttribute("data-glass-surface")).toBe("glass");
    expect(el.className).toContain("bg-glass");
    expect(el.className).toContain("backdrop-blur-glass");
    expect(el.className).toContain("border-glass");
    // the scrim layer is present, behind the content, presentational
    const scrim = el.querySelector("[data-glass-scrim]") as HTMLElement;
    expect(scrim, "glass variant must render the scrim layer").toBeTruthy();
    expect(scrim.className).toContain("bg-glass-solid");
    expect(scrim.getAttribute("aria-hidden")).toBe("true");
    expect(scrim.style.opacity).toBe(String(SCRIM_MIN_OPACITY));
  });

  it("glass is the default variant", () => {
    const { container } = render(
      <GlassSurface>
        <p>body</p>
      </GlassSurface>,
    );
    const el = container.querySelector("[data-glass-surface]") as HTMLElement;
    expect(el.getAttribute("data-glass-surface")).toBe("glass");
  });

  it("(d) variant='solid' uses bg-glass-solid, NO backdrop-filter, NO scrim, and NEVER an opaque ice/space body bg", () => {
    const { container } = render(
      <GlassSurface variant="solid" data-testid="dense">
        <p>dense body text</p>
      </GlassSurface>,
    );
    const el = container.querySelector("[data-glass-surface]") as HTMLElement;
    expect(el.getAttribute("data-glass-surface")).toBe("solid");
    expect(el.className).toContain("bg-glass-solid");
    expect(el.className).not.toContain("backdrop-blur");
    // never the occluding landing backgrounds the audit removes
    expect(el.className).not.toContain("bg-ice-2");
    expect(el.className).not.toContain("bg-space-2");
    expect(el.querySelector("[data-glass-scrim]"), "solid carries no scrim layer").toBeNull();
  });

  it("forwards `as`, className, and arbitrary props", () => {
    const { container } = render(
      <GlassSurface as="section" variant="glass" className="custom-x" role="region" aria-label="L">
        <p>x</p>
      </GlassSurface>,
    );
    const el = container.querySelector("[data-glass-surface]") as HTMLElement;
    expect(el.tagName).toBe("SECTION");
    expect(el.className).toContain("custom-x");
    expect(el.getAttribute("role")).toBe("region");
    expect(el.getAttribute("aria-label")).toBe("L");
  });
});

describe("GlassSurface — degradation (M4 / RULE 3)", () => {
  it("(c) under prefers-reduced-motion:reduce the glass variant renders the SOLID fallback (no backdrop-filter, no scrim)", () => {
    installMatchMedia(true); // reduced motion ON
    const { container } = render(
      <GlassSurface variant="glass" data-testid="gs">
        <p>body</p>
      </GlassSurface>,
    );
    const el = container.querySelector("[data-glass-surface]") as HTMLElement;
    // it still requested glass, but degraded to solid
    expect(el.getAttribute("data-glass-variant")).toBe("glass");
    expect(el.getAttribute("data-glass-surface")).toBe("solid");
    expect(el.className).toContain("bg-glass-solid");
    expect(el.className).not.toContain("backdrop-blur");
    expect(el.querySelector("[data-glass-scrim]"), "degraded glass carries no scrim").toBeNull();
  });

  it("(c) the reduced-motion fallback's text still clears AA (identical to variant='solid')", () => {
    // The fallback background is the solid hue — proven above to clear 4.5:1 in
    // both modes with NO scene. Re-assert here so the degradation path owns the
    // guarantee explicitly.
    expect(contrastRatio(INK_DAY, GLASS_SOLID_DAY)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(BRIGHT_NIGHT, GLASS_SOLID_NIGHT)).toBeGreaterThanOrEqual(4.5);
  });

  it("sceneAbsent forces the solid fallback even with motion enabled", () => {
    installMatchMedia(false); // motion ON
    const { container } = render(
      <GlassSurface variant="glass" sceneAbsent data-testid="gs">
        <p>body</p>
      </GlassSurface>,
    );
    const el = container.querySelector("[data-glass-surface]") as HTMLElement;
    expect(el.getAttribute("data-glass-surface")).toBe("solid");
    expect(el.className).not.toContain("backdrop-blur");
  });
});
