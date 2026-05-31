/**
 * token-retone.spec.ts — the AMS-SPR-09 EXPERIENCE GATE (RULE 2: prove the
 * weathered re-tone in a REAL browser, not only in a vitest).
 *
 * THE OPERATOR ASK SPR-09 SHIPS
 * -----------------------------
 * Dial the bold lemon back to a softer, weathered "light" across the var-driven
 * ACCENT / HIGHLIGHT roles — while keeping the bottom-tab yellow LOUD. The
 * unit floor (src/design/tokens.contrast.test.ts) proves the AA math on the
 * token exports; THIS gate proves the same facts on the live rendered app:
 *
 *   (1) the var-driven chrome accents are RE-TONED — the resolved
 *       `--sun-glow` / `--sun-deep` / `--sun-hl-*` / the new `--sun-light` on
 *       the live :root are the softer weathered values, and crucially NOT the
 *       loud brand `--sun` (#F5DF24). A regression that reverted any of them to
 *       the lemon reddens here.
 *   (2) the bottom tab stays LOUD — the real bottom rail's accent edge
 *       (NavRail `border-sun`, → the unchanged brand lemon) resolves to the
 *       bold #F5DF24, and `--bar-accent` / `--sun` are unchanged. The bar must
 *       NOT have softened with the chrome.
 *   (3) text stays LEGIBLE — the landing heading still clears WCAG-AA 4.5:1
 *       over its (glass-scrimmed) background via the shared assertContrast,
 *       computed over the worst-case scene. Re-toning the token values must not
 *       cost any consumed text pair its AA.
 *
 * Reads token VALUES via getComputedStyle on the live :root (layout-independent
 * — the durable way to prove an app-wide token change, vs sampling a single
 * pixel whose position drifts with layout). assertContrast is the EXISTING
 * shared helper (e2e/_ams/visible.ts) — same WCAG math the unit floor reuses.
 *
 * RUNS UNDER: the `ams-real` Playwright project (real SPA via vite preview
 * :4173). On a sandbox with no served SPA the project skips cleanly (RULE 3).
 */

import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import { assertContrast } from "./_ams/visible";

const DEFAULT_ROUTE = "/";

/** The bottom rail (NavRail.tsx: aria-label="Primary navigation"). */
const RAIL = 'aside[aria-label="Primary navigation"]';

/** The brand lemon — the one value SPR-09 must NOT change (bar + Werner). */
const BRAND_LEMON = "#F5DF24";

/** Read resolved :root custom properties from the live document. */
async function rootVars(page: import("@playwright/test").Page, names: readonly string[]) {
  return page.evaluate((vars) => {
    const cs = getComputedStyle(document.documentElement);
    const out: Record<string, string> = {};
    for (const v of vars) out[v] = cs.getPropertyValue(v).trim();
    return out;
  }, names);
}

/** Normalise a CSS colour string to lowercase, whitespace-free for comparison. */
const norm = (s: string) => s.toLowerCase().replace(/\s+/g, "");

/** Parse "#RRGGBB" or "rgb(r, g, b)" → {r,g,b}. Returns null if unparseable. */
function toRgb(s: string): { r: number; g: number; b: number } | null {
  const h = s.trim().match(/^#([0-9a-f]{6})$/i);
  if (h) {
    const v = h[1];
    return { r: parseInt(v.slice(0, 2), 16), g: parseInt(v.slice(2, 4), 16), b: parseInt(v.slice(4, 6), 16) };
  }
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const p = m[1].split(",").map((x) => parseFloat(x.trim()));
    return { r: p[0] ?? 0, g: p[1] ?? 0, b: p[2] ?? 0 };
  }
  return null;
}

/** Rough chroma (max−min channel, 0…1) — loudness proxy. */
function chroma(c: { r: number; g: number; b: number }): number {
  return (Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b)) / 255;
}

test.describe("AMS-SPR-09 — weathered chrome, loud bar (real browser)", () => {
  test("(1) the var-driven chrome accents are re-toned, NOT the loud lemon", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const v = await rootVars(page, [
      "--sun",
      "--sun-light",
      "--sun-glow",
      "--sun-deep",
      "--sun-hl-day",
      "--sun-hl-faint",
    ]);

    // --sun itself is the brand constant — unchanged.
    expect(norm(v["--sun"]), `--sun must stay the brand lemon (got ${v["--sun"]})`).toBe(
      norm(BRAND_LEMON),
    );

    // The new weathered light ramp exists and is softer than the brand.
    expect(v["--sun-light"], "--sun-light (the new weathered ramp) must be defined").not.toBe("");
    const light = toRgb(v["--sun-light"])!;
    const lemon = toRgb(v["--sun"])!;
    expect(
      chroma(light),
      `--sun-light (${v["--sun-light"]}) must be LOWER chroma than the brand lemon (${v["--sun"]})`,
    ).toBeLessThan(chroma(lemon));

    // The re-toned accent/highlight roles must NOT equal the loud brand lemon.
    for (const role of ["--sun-glow", "--sun-deep"]) {
      expect(
        norm(v[role]),
        `${role} (${v[role]}) must be RE-TONED off the loud --sun (${v["--sun"]})`,
      ).not.toBe(norm(BRAND_LEMON));
    }
    // The highlighter veils must be the weathered rgb, not the brand-lemon rgb.
    expect(
      norm(v["--sun-hl-day"]),
      `--sun-hl-day (${v["--sun-hl-day"]}) must be the weathered veil, not the lemon`,
    ).not.toContain("245,223,36");
    expect(norm(v["--sun-hl-faint"])).not.toContain("245,223,36");
  });

  test("(2) the bottom tab stays LOUD — its accent edge is the bold #F5DF24", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    const rail = page.locator(RAIL).first();
    await expect(rail, "the bottom rail must be on screen").toBeVisible({ timeout: 5_000 });

    // --bar-accent (day) + --sun resolve to the unchanged loud lemon.
    const v = await rootVars(page, ["--bar-accent", "--sun"]);
    expect(norm(v["--sun"]), "--sun is the brand constant").toBe(norm(BRAND_LEMON));
    // --bar-accent → var(--sun) on day; resolves to the lemon.
    const bar = toRgb(v["--bar-accent"]);
    if (bar) {
      expect(chroma(bar), `--bar-accent (${v["--bar-accent"]}) must stay LOUD chroma`).toBeGreaterThan(
        0.6,
      );
    }

    // PROVE on real pixels-of-style: the rail's accent edge (NavRail border-sun)
    // is the bold lemon, not a softened tone. The bar is `bg-ink … border-?-edge
    // border-sun`; read whichever border side carries the sun edge.
    const edge = await rail.evaluate((el) => {
      const cs = getComputedStyle(el as Element);
      // The bottom rail draws its sun edge on the TOP border; the side rail on
      // the RIGHT. Return all four so the assertion can find the painted one.
      return {
        top: cs.borderTopColor,
        right: cs.borderRightColor,
        bottom: cs.borderBottomColor,
        left: cs.borderLeftColor,
      };
    });
    const lemonRgb = toRgb(BRAND_LEMON)!;
    const sides = [edge.top, edge.right, edge.bottom, edge.left]
      .map(toRgb)
      .filter((c): c is { r: number; g: number; b: number } => c !== null);
    const carriesLemon = sides.some(
      (c) =>
        Math.abs(c.r - lemonRgb.r) <= 2 &&
        Math.abs(c.g - lemonRgb.g) <= 2 &&
        Math.abs(c.b - lemonRgb.b) <= 2,
    );
    expect(
      carriesLemon,
      `the bottom rail must carry the LOUD #F5DF24 accent edge (border-sun); got sides ` +
        `${JSON.stringify(edge)} — SPR-09 must not have softened the bar`,
    ).toBe(true);

    // Durable proof artifact: the real loud bottom rail after the re-tone.
    await rail.screenshot({ path: "test-results/token-retone-loud-bar.png" });
  });

  test("(3) text stays legible — the landing heading clears WCAG-AA over its glass", async ({
    page,
  }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // The same shared over-scene contrast gate SPR-03 proves — re-run here so a
    // token VALUE change that eroded any consumed text pair reddens this gate.
    await assertContrast(page, "h1", 4.5);
  });
});
