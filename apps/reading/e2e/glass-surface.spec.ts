/**
 * glass-surface.spec.ts — the SPR-03 headline gate (real app, real route).
 *
 * WHY THIS EXISTS (RULE 2 — prove it in a browser, or it isn't done)
 * ------------------------------------------------------------------
 * AMS-v1 shipped INVISIBLE because NOTHING ever loaded the real app on the real
 * default route and asserted "a mountain is visible." This spec does exactly
 * that, on `/` (App.tsx: "/" → ResearchWorkstation → StartResearch idle), via
 * loginAndGotoApp (mocked /auth/me, no app-code bypass, KEY-FREE scene).
 *
 * Three facts, all proven on real pixels / real computed contrast:
 *   1. the mountain is VISIBLE — a CONTENT-FREE scene region (the gap BETWEEN
 *      the left ad-border rail and the centred content column) is NOT one flat
 *      ice/space colour.
 *   2. that region is NON-VACUOUS — a live negative control hides the z-0 scene
 *      canvas and asserts the SAME region collapses to one flat colour. This is
 *      the durable defence the SPR-01 sharpen demands: it proves the variance in
 *      fact (1) comes from the MOUNTAIN, not from chrome/text leaking into the
 *      band. (The first cut sampled x 0.02–0.16, which overlapped the opaque
 *      AdBorder left rail + its "From the library" creative TEXT — variance was
 *      ~933 with the scene shown AND ~680 with it HIDDEN, a false green. This
 *      control makes that class of regression impossible to ship silently.)
 *   3. body text stays LEGIBLE — the route heading clears WCAG-AA 4.5:1 over its
 *      (glass-scrimmed) background, composited over the worst-case scene.
 *
 * THE CONTENT-FREE REGION — geometry (verified live, vp 1280×720)
 * ---------------------------------------------------------------
 * AdBorder (AppShell mount) paints opaque rails WITH creative text in all four
 * insets: top y∈[0,36], bottom y∈[684,720], left x∈[0,96], right x∈[1184,1280]
 * (left/right rails appear at the xl/lg tier). The SceneChrome action bar sits
 * at y∈[80,154]; below it the SceneChrome glass band (bg-glass over the z-0
 * scene) fills the working region. The idle `/` content is the centred
 * GlassSurface column at x∈[256,1024]. So the gap x∈[~109,231], y∈[216,562]
 * (fractions x 0.085–0.18, y 0.30–0.78) lies BETWEEN the left ad rail (ends
 * x=96) and the content column (starts x=256), BELOW the action bar (ends
 * y=154) and ABOVE the bottom rail (starts y=684). The ONLY thing painted there
 * is the translucent SceneChrome glass band over the moving scene — no opaque
 * chrome, no creative text, no heading. The negative control (test 2) proves
 * this empirically: with the scene hidden the band's variance falls to 0.
 *
 * RUNS UNDER: the `ams-real` Playwright project (real SPA via vite preview
 * :4173), NOT chromium/Storybook. `npm run e2e:ams` or
 * `playwright test --project=ams-real`.
 */

import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import {
  assertSceneVisible,
  assertContrast,
  SCENE_SOLID_VARIANCE_THRESHOLD,
  SCENE_SOLID_DISTINCT_FLOOR,
  decodePng,
  regionVariance,
  distinctColors,
} from "./_ams/visible";

const DEFAULT_ROUTE = "/";

/**
 * A CONTENT-FREE scene region (viewport fractions) — the gap between the left
 * ad-border rail (ends x≈0.075) and the centred content column (starts x≈0.20),
 * below the SceneChrome action bar (ends y≈0.214) and above the bottom ad rail
 * (starts y≈0.95). At the default 1280×720 viewport this is px x∈[109,231],
 * y∈[216,562]: ONLY the translucent SceneChrome glass band over the z-0 scene —
 * provably no opaque chrome, no creative text, no heading. Non-vacuity is
 * enforced by the negative-control test below, not merely asserted in prose.
 */
const SCENE_MARGIN_REGION = { x: 0.085, y: 0.3, width: 0.095, height: 0.48 } as const;

test.describe("SPR-03 — landing glass reveals the scene + keeps text legible", () => {
  test("the mountain is visible in a content-free band on /", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await assertSceneVisible(page, SCENE_MARGIN_REGION);
  });

  test("negative control: the SAME band goes flat when the scene is hidden (non-vacuity)", async ({
    page,
  }) => {
    // The durable defence against a margin region silently capturing chrome/text
    // (the exact v1 false green). We sample the chosen band twice on the real
    // page: once with the z-0 scene painting, once with it visibility:hidden.
    // A truly scene-only band MUST flip from non-solid → solid. If it stays
    // non-solid with the scene hidden, the variance is coming from something
    // OTHER than the mountain (chrome/text), and the headline assertion above
    // would be vacuous — so this reddens.
    await loginAndGotoApp(page, DEFAULT_ROUTE);

    const vp = page.viewportSize() ?? { width: 1280, height: 720 };
    const clip = {
      x: Math.round(SCENE_MARGIN_REGION.x * vp.width),
      y: Math.round(SCENE_MARGIN_REGION.y * vp.height),
      width: Math.round(SCENE_MARGIN_REGION.width * vp.width),
      height: Math.round(SCENE_MARGIN_REGION.height * vp.height),
    };

    const sample = async () => {
      const img = decodePng(await page.screenshot({ clip }));
      return { v: regionVariance(img), c: distinctColors(img) };
    };

    // 1) Scene PAINTING → the band must NOT be a flat colour (mountain visible).
    const withScene = await sample();
    const visibleSolid =
      withScene.v < SCENE_SOLID_VARIANCE_THRESHOLD &&
      withScene.c <= SCENE_SOLID_DISTINCT_FLOOR;
    expect(
      visibleSolid,
      `non-vacuity precondition: with the scene PAINTING the band is already flat ` +
        `(variance=${withScene.v.toFixed(1)}, distinctColors=${withScene.c}); the region is not on the scene`,
    ).toBe(false);

    // 2) Hide the z-0 scene canvas, then re-sample the SAME band. Now the only
    //    thing left in this gap is the translucent SceneChrome glass band over
    //    an empty backdrop → one flat colour. If it is NOT flat, the band is
    //    capturing chrome/text and the headline gate is vacuous.
    await page.evaluate(() => {
      const scene = document.querySelector('[data-testid="scene-root"]');
      if (scene instanceof HTMLElement) scene.style.visibility = "hidden";
    });
    await page.waitForTimeout(300);
    const withoutScene = await sample();
    const hiddenSolid =
      withoutScene.v < SCENE_SOLID_VARIANCE_THRESHOLD &&
      withoutScene.c <= SCENE_SOLID_DISTINCT_FLOOR;
    expect(
      hiddenSolid,
      `VACUOUS GATE: with the z-0 scene HIDDEN the band is still NOT flat ` +
        `(variance=${withoutScene.v.toFixed(1)} ≥ ${SCENE_SOLID_VARIANCE_THRESHOLD} or ` +
        `distinctColors=${withoutScene.c} > ${SCENE_SOLID_DISTINCT_FLOOR}). The region overlaps ` +
        `chrome/text, so the "mountain is visible" assertion passes on non-scene variance ` +
        `(this is the v1 false green the SPR-01 sharpen forbids). Move the region off the chrome.`,
    ).toBe(true);
  });

  test("the landing heading clears WCAG-AA 4.5:1 over its glass background", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // The idle `/` home heading (StartResearch.tsx "What do you want to
    // research?"). Its text-over-surface contrast must clear AA — the scrim the
    // GlassSurface primitive owns is what guarantees this over the moving scene
    // (worst case ≈10.55:1 day-glass-over-black, the bound GlassSurface.test.tsx
    // proves and assertContrast recomputes from the live token values).
    await assertContrast(page, "h1", 4.5);
  });
});
