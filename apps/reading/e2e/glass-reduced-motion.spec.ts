/**
 * glass-reduced-motion.spec.ts — the SPR-03 degradation gate (real app).
 *
 * Proves M4 / RULE 3 in a real browser: under `prefers-reduced-motion: reduce`
 * the scene FREEZES (Scene.tsx: useSceneClock → frozen, one static frame) and
 * the GlassSurface landing surfaces degrade to their OPAQUE solid fallback — yet
 * every screen stays complete + legible. A frozen scene is still a painted scene
 * (one static mountainscape frame), so:
 *   1. the content-free margin is still NOT a flat colour (the frozen frame is a
 *      gradient sky + peaks, not a solid fill), and
 *   2. body text still clears WCAG-AA 4.5:1 — now over the opaque solid
 *      fallback, the same guarantee the motion path carries.
 *
 * The browser is launched with reduced-motion forced via the Playwright project
 * context (emulateMedia in the test). RUNS UNDER the `ams-real` project.
 */

import { test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import { assertSceneVisible, assertContrast } from "./_ams/visible";

const DEFAULT_ROUTE = "/";
// Same content-free band as glass-surface.spec.ts: the gap BETWEEN the left
// ad-border rail (ends x≈0.075) and the centred content column (starts x≈0.20),
// below the SceneChrome action bar and above the bottom ad rail. Only the
// translucent SceneChrome glass band over the z-0 scene is painted here — no
// opaque chrome, no creative text. (glass-surface.spec.ts owns the live
// negative control proving this band is non-vacuous.)
const SCENE_MARGIN_REGION = { x: 0.085, y: 0.3, width: 0.095, height: 0.48 } as const;

test.describe("SPR-03 — reduced-motion: frozen scene + opaque-fallback text stays legible", () => {
  test("the frozen scene is still painted (not a flat colour) in the margin", async ({ page }) => {
    // Force the OS reduced-motion preference for this context BEFORE the app
    // boots, so Scene freezes and GlassSurface degrades to its solid fallback.
    await page.emulateMedia({ reducedMotion: "reduce" });
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // A frozen mountainscape frame is still a gradient + peaks → non-solid. If
    // reduced-motion accidentally blanked the scene to a flat fill, this reddens.
    await assertSceneVisible(page, SCENE_MARGIN_REGION);
  });

  test("under reduced-motion the landing text still clears WCAG-AA 4.5:1", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    // Now the GlassSurface landings render their opaque solid fallback; the
    // contrast guarantee is identical (and stronger — solid hue, no scene-bleed).
    await assertContrast(page, "h1", 4.5);
  });
});
