/**
 * spacing-density test (CFEEL-S2 M1) — proves the density-overridable spacing
 * mechanism is (a) DEFAULT pixel-identical to Tailwind's stock scale and
 * (b) genuinely overridable per subtree via [data-density].
 *
 * WHY THIS IS A REAL TEST, NOT A STRING MATCH (rigor): the danger with a
 * "redefine the whole spacing scale as calc(var(--spacing) * N)" change is a
 * silent default-surface SHIFT — a dropped key, or a wrong multiplier, would
 * move pixels on the shipped UI (a lostpixel-gate failure). So this test does
 * not assert the config STRING. It:
 *
 *   1. Loads the Tailwind config for real and, for a
 *      representative set of utilities, evaluates calc(var(--spacing) * N) with
 *      --spacing taken from the REAL tokens.css :root (parsed at runtime), then
 *      asserts the resolved length equals Tailwind's OWN default for that key.
 *      This is the default-identity proof: p-4 == 1rem, gap-2 == 0.5rem,
 *      m-1 == 0.25rem — computed, not asserted as a literal config string.
 *   2. Uses jsdom getComputedStyle to confirm --spacing actually CASCADES:
 *      0.25rem at :root, and a strictly SMALLER value inside a
 *      [data-density="compact"] subtree (the override works and is scoped).
 *
 * jsdom note: jsdom does not lay out calc()/var() into px (getComputedStyle on
 * `padding` returns "0"), but it DOES resolve CSS custom properties through the
 * cascade — so we read --spacing via getPropertyValue and do the rem arithmetic
 * ourselves. That keeps the value REAL (the var comes from the actual CSS) while
 * sidestepping jsdom's missing layout engine.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import defaultTheme from "tailwindcss/defaultTheme";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/src/design
const APP = join(here, "..", ".."); // apps/reading
const TOKENS_CSS = readFileSync(join(here, "tokens.css"), "utf8");
// Load the Tailwind config at runtime (it is plain JS with no .d.ts); typed as
// `unknown` and read as config data, never regex-string-matched.
const require = createRequire(import.meta.url);
const tailwindConfig = require(join(APP, "tailwind.config.js"));

/** Strip /* … *\/ comments so a commented-out declaration can't be read live. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** First live `--name: <value>;` inside the `:root { … }` block (the default
 *  theme). Comment-safe. */
function rootCssVar(name: string): string | null {
  const live = stripComments(TOKENS_CSS);
  // Grab the first :root { … } body (the default day block).
  const rootBody = live.match(/:root\s*\{([\s\S]*?)\}/);
  if (!rootBody) return null;
  const m = rootBody[1].match(new RegExp(`--${name}\\s*:\\s*([^;]+);`));
  return m ? m[1].trim() : null;
}

/** First live `--name: <value>;` inside the [data-density="compact"] rule. */
function compactCssVar(name: string): string | null {
  const live = stripComments(TOKENS_CSS);
  const body = live.match(/\[data-density="compact"\]\s*\{([\s\S]*?)\}/);
  if (!body) return null;
  const m = body[1].match(new RegExp(`--${name}\\s*:\\s*([^;]+);`));
  return m ? m[1].trim() : null;
}

/** Parse a CSS rem length like "0.25rem" → number of rem. Throws on non-rem. */
function rem(value: string): number {
  const m = value.trim().match(/^([0-9]*\.?[0-9]+)rem$/);
  if (!m) throw new Error(`not a rem length: "${value}"`);
  return Number(m[1]);
}

/** The config's spacing[key] is "calc(var(--spacing) * N)" (or a literal for
 *  the 0 / px keys). Pull the N multiplier, or null for the literal keys. */
function spacingMultiplier(configValue: string): number | null {
  const m = configValue.match(/var\(--spacing\)\s*\*\s*([0-9]*\.?[0-9]+)/);
  return m ? Number(m[1]) : null;
}

// Resolve the REAL Tailwind config (not a regex over the file).
let resolvedSpacing: Record<string, string>;
let defaultSpacing: Record<string, string>;
let rootSpacingRem: number;

beforeAll(() => {
  const cfg = tailwindConfig.default ?? tailwindConfig;
  resolvedSpacing = (cfg as { theme: { extend: { spacing: Record<string, string> } } }).theme
    .extend.spacing;
  defaultSpacing = (defaultTheme as { spacing: Record<string, string> }).spacing;
  const root = rootCssVar("spacing");
  expect(root, "tokens.css :root must define --spacing").toBeTruthy();
  rootSpacingRem = rem(root as string); // 0.25
});

describe("spacing density — DEFAULT identity (no pixel shift)", () => {
  it("tokens.css :root --spacing is 0.25rem (== Tailwind's base spacing unit)", () => {
    expect(rootSpacingRem).toBe(0.25);
  });

  it("the full default Tailwind spacing scale is enumerated (no dropped key)", () => {
    // A dropped key would silently disappear that utility → a shift. Assert the
    // config covers EVERY default Tailwind spacing key.
    const defaultKeys = Object.keys(defaultSpacing);
    for (const k of defaultKeys) {
      expect(
        resolvedSpacing[k],
        `spacing key "${k}" must be present in the redefined scale`,
      ).toBeTruthy();
    }
  });

  it("representative utilities resolve byte-identically to Tailwind defaults", () => {
    // Compute the resolved length from the REAL var (rootSpacingRem, parsed from
    // tokens.css) × the REAL config multiplier, and compare to Tailwind's OWN
    // default for that key. p-4, gap-2, m-1 all share the `spacing` scale.
    const cases: Array<[string, number]> = [
      ["4", 1], // p-4 → 1rem
      ["2", 0.5], // gap-2 → 0.5rem
      ["1", 0.25], // m-1 → 0.25rem
      ["0.5", 0.125], // half-step still exact
      ["8", 2], // p-8 → 2rem
      ["96", 24], // the largest key → 24rem
    ];
    for (const [key, expectedRem] of cases) {
      const mult = spacingMultiplier(resolvedSpacing[key]);
      expect(mult, `spacing["${key}"] must be calc(var(--spacing) * N)`).not.toBeNull();
      const resolved = rootSpacingRem * (mult as number);
      expect(resolved, `resolved spacing["${key}"]`).toBeCloseTo(expectedRem, 10);
      // And it must equal Tailwind's own default for the key (the identity).
      expect(rem(defaultSpacing[key])).toBeCloseTo(resolved, 10);
    }
  });

  it("the 0 and px keys stay pixel-literal (not a calc that could drift)", () => {
    expect(resolvedSpacing["0"]).toBe("0px");
    expect(resolvedSpacing["px"]).toBe("1px");
  });
});

describe("spacing density — the [data-density] override actually cascades", () => {
  it("--spacing resolves smaller inside a [data-density='compact'] subtree", () => {
    // Inject the real :root + compact rules and read --spacing through the
    // cascade with jsdom getComputedStyle (a REAL resolved value, not a string).
    const rootDecl = rootCssVar("spacing") as string;
    const compactDecl = compactCssVar("spacing");
    expect(compactDecl, "tokens.css must define [data-density='compact'] --spacing").toBeTruthy();

    const style = document.createElement("style");
    style.textContent = `
      :root { --spacing: ${rootDecl}; }
      [data-density="compact"] { --spacing: ${compactDecl}; }
    `;
    document.head.appendChild(style);

    const outer = document.createElement("div"); // default density
    const inner = document.createElement("div"); // inside compact subtree
    const compactWrap = document.createElement("div");
    compactWrap.setAttribute("data-density", "compact");
    compactWrap.appendChild(inner);
    document.body.appendChild(outer);
    document.body.appendChild(compactWrap);

    const rootResolved = getComputedStyle(document.documentElement).getPropertyValue("--spacing").trim();
    const outerResolved = getComputedStyle(outer).getPropertyValue("--spacing").trim();
    const innerResolved = getComputedStyle(inner).getPropertyValue("--spacing").trim();

    // Default surface unchanged.
    expect(rem(rootResolved)).toBe(0.25);
    expect(rem(outerResolved)).toBe(0.25);
    // Compact subtree is strictly denser.
    expect(rem(innerResolved)).toBeLessThan(0.25);

    // Cleanup so we don't leak the injected style into other tests.
    document.head.removeChild(style);
    document.body.removeChild(outer);
    document.body.removeChild(compactWrap);
  });

  it("compact --spacing is the ~12.5%-denser value (≈3.5px vs 4px)", () => {
    const compactDecl = compactCssVar("spacing") as string;
    const compactRem = rem(compactDecl);
    // 0.21875rem ≈ 3.5px at a 16px root; ~12.5% below the 0.25rem default.
    expect(compactRem).toBeLessThan(0.25);
    expect(compactRem / 0.25).toBeCloseTo(0.875, 5); // ~12.5% denser
  });
});
