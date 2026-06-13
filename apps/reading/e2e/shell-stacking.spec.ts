/**
 * shell-stacking.spec.ts — ALC SPR-08 M1: the F-1 occlusion regression, encoded.
 *
 * WHAT F-1 ACTUALLY IS (rigor #1 — reproduce before theorizing the fix)
 * --------------------------------------------------------------------
 * F-1 (docs/mountain-shell-verification.md §"Open defects") is a floating-window
 * vs bottom-bar z-stacking hazard that was UNDOCUMENTED and TIER-INCONSISTENT:
 *
 *   - DESKTOP: the bottom NavRail is a STATIC flex sibling (z:auto). The windows
 *     layer is `position:absolute z-30` and a window declares `WINDOW_Z_BASE+z`
 *     (40+). A positioned, z-indexed layer out-paints a static sibling, so a
 *     window painted OVER the rail → the rail (the nav chrome) was OCCLUDED.
 *   - MOBILE (sm/md): the rail becomes `position:absolute z-40` (NavRail.tsx),
 *     which OUTRANKS the windows layer's `z-30` floor → the OPPOSITE: the rail
 *     occluded the window.
 *
 * So the same drag produced opposite results by tier, and neither was a stated
 * contract — the "presumed mitigation" (windows mount in the working region) was
 * UNCONFIRMED by a real browser. The canonical order the shell wants is
 * scene < windows < BARS (the nav rail must always stay reachable). The fix
 * (shell/zScale.ts) puts the whole windows band STRICTLY BELOW the bars band on
 * EVERY tier, so the rail consistently paints over a window and is never hidden.
 *
 * THE PROOF (a compositor fact jsdom cannot produce)
 * --------------------------------------------------
 * On DESKTOP — the tier whose PRE-FIX behaviour VIOLATED the canonical order —
 * open a window, drive it (keyboard) until it overlaps the bottom rail band,
 * then read `document.elementsFromPoint` (top-first) at a shared pixel and
 * assert the RAIL paints ABOVE the window (railIdx < winIdx). Pre-fix this is
 * RED (the desktop window out-painted the static rail); post-fix GREEN (windows
 * band < bars band). The roaming PenguinMascot (werner band, above both) is
 * allowed on top — we compare the rail vs the window only.
 *
 * RUN: belongs to the `ams-real` Playwright project (needs the real served SPA
 * for a real compositor). When AMS_APP_URL is unset + no server boots, the
 * project skips cleanly. Added to ams-real testMatch + chromium testIgnore.
 */

import { expect, test, type Page } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

const DEFAULT_ROUTE = "/";

/** Open the launcher (the single non-workflow rail affordance) + spawn a window. */
async function openAWindow(page: Page): Promise<void> {
  await page.getByRole("button", { name: "More" }).first().click();
  await expect(page.getByRole("dialog", { name: "More" })).toBeVisible();
  await page
    .getByRole("button", { name: /open research workflow in a window/i })
    .first()
    .click();
  await expect(
    page.locator('[data-windows-layer] [role="dialog"][data-window-mode]').first(),
  ).toBeVisible({ timeout: 5_000 });
}

test.describe("ALC SPR-08 M1 — shell stacking: the nav rail is never occluded by a window (F-1)", () => {
  test("on desktop, the bottom rail paints ABOVE a window dragged into its band", async ({ page }) => {
    // Desktop tier (≥ lg): this is where the pre-fix behaviour VIOLATED the
    // canonical order — a positioned z-30 window layer out-painted the static
    // rail, hiding the nav chrome. The fix makes windows < bars here too.
    await page.setViewportSize({ width: 1280, height: 800 });
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await openAWindow(page);

    const win = page
      .locator('[data-windows-layer] [data-workspace-window]')
      .first();
    await expect(win).toBeVisible();

    // Focus the window chrome (title bar) so the keyboard window-mover is armed.
    const titleBar = page
      .locator('[data-windows-layer] [data-window-titlebar]')
      .first();
    await titleBar.focus();

    const rail = page.locator('aside[aria-label="Primary navigation"]').first();
    await expect(rail).toBeVisible();
    const railBox = await rail.boundingBox();
    expect(railBox, "rail has no box").not.toBeNull();
    if (!railBox) return;

    // Drive the window DOWN one ArrowDown (24px) at a time until its TITLE BAR
    // enters the rail's vertical band, so window chrome and rail share pixels.
    // Bounded loop so a layout change can't hang the test.
    let titleBarBox = await titleBar.boundingBox();
    for (let i = 0; i < 60 && titleBarBox; i++) {
      const tbMid = titleBarBox.y + titleBarBox.height / 2;
      if (tbMid >= railBox.y && tbMid <= railBox.y + railBox.height) break;
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(20);
      titleBarBox = await titleBar.boundingBox();
    }
    await page.waitForTimeout(80);
    titleBarBox = await titleBar.boundingBox();
    expect(titleBarBox, "title bar has no box").not.toBeNull();
    if (!titleBarBox) return;

    // The vertical overlap band between the window TITLE BAR and the rail.
    const overlapTop = Math.max(titleBarBox.y, railBox.y);
    const overlapBottom = Math.min(
      titleBarBox.y + titleBarBox.height,
      railBox.y + railBox.height,
    );
    expect(
      overlapBottom - overlapTop,
      `window title bar (${Math.round(titleBarBox.y)}…${Math.round(titleBarBox.y + titleBarBox.height)}) and ` +
        `rail (${Math.round(railBox.y)}…${Math.round(railBox.y + railBox.height)}) do not overlap vertically — ` +
        `the repro could not position the window over the rail band`,
    ).toBeGreaterThan(2);

    // A sample point inside BOTH boxes, biased toward the shared x interval and
    // the middle of the overlap band.
    const xLo = Math.max(titleBarBox.x, railBox.x);
    const xHi = Math.min(
      titleBarBox.x + titleBarBox.width,
      railBox.x + railBox.width,
    );
    const sampleX = Math.round((xLo + xHi) / 2);
    const sampleY = Math.round((overlapTop + overlapBottom) / 2);

    // The compositor truth: the FULL paint stack at that pixel, top-first. We
    // compare the first rail-descendant vs the first window-descendant. The
    // roaming PenguinMascot (werner band) may legitimately sit above both, so we
    // require ONLY that the RAIL out-paints the WINDOW (the canonical order).
    const order = await page.evaluate(
      ([x, y]) => {
        const els = document.elementsFromPoint(x, y) as HTMLElement[];
        let winIdx = -1;
        let railIdx = -1;
        for (let i = 0; i < els.length; i++) {
          const el = els[i];
          if (winIdx === -1 && el.closest("[data-workspace-window]")) winIdx = i;
          if (
            railIdx === -1 &&
            el.closest('aside[aria-label="Primary navigation"]')
          )
            railIdx = i;
        }
        return {
          winIdx,
          railIdx,
          stack: els
            .slice(0, 8)
            .map((e) => `${e.tagName.toLowerCase()}.${(e.className?.toString?.() ?? "").split(" ")[0]}`),
        };
      },
      [sampleX, sampleY],
    );

    // Both must be present in the stack at this shared pixel.
    expect(
      order.railIdx,
      `the rail is not in the paint stack at (${sampleX},${sampleY}); stack=${JSON.stringify(order.stack)}`,
    ).toBeGreaterThanOrEqual(0);
    expect(
      order.winIdx,
      `the window is not in the paint stack at (${sampleX},${sampleY}); stack=${JSON.stringify(order.stack)}`,
    ).toBeGreaterThanOrEqual(0);

    // elementsFromPoint is TOP-FIRST → a LOWER index paints HIGHER. The canonical
    // order is windows < bars, so the RAIL must paint above the window:
    // railIdx < winIdx.
    expect(
      order.railIdx < order.winIdx,
      `F-1: at the overlap pixel (${sampleX},${sampleY}) the floating WINDOW paints ABOVE the bottom ` +
        `NavRail (railIdx=${order.railIdx}, winIdx=${order.winIdx}; stack=${JSON.stringify(order.stack)}). ` +
        `The window's positioned z-30/40+ layer out-paints the rail, hiding the nav chrome. The zScale (M1) ` +
        `must place the windows band STRICTLY BELOW the bars band on every tier so the rail is always reachable.`,
    ).toBe(true);
  });
});
