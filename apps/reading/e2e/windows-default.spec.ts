/**
 * windows-default.spec.ts — SPR-04 (the windows-default keystone) BROWSER gate.
 *
 * WHY THIS EXISTS (rigor #3 — prove it in a browser, or it isn't done)
 * --------------------------------------------------------------------
 * windowContract.test.tsx (jsdom, no compositor) proves the policy INVERSION at
 * the call site: a within-contract product click calls windowsStore.open()
 * instead of navigate(). It CANNOT prove the operator's actual complaint is
 * fixed — that a window is VISIBLE over the moving scene, that the glass body
 * lets the scene show through, and that three windows coexist. Those are
 * compositor facts. This Playwright spec loads the REAL authed SPA (via
 * loginAndGotoApp, no app-code bypass) and asserts them against real pixels +
 * real DOM — the load-bearing artifact that the inversion landed.
 *
 * THREE PROOFS (the SPR-04 experience gates):
 *   1. click product  → a sub-action window is on screen (the DEFAULT, no ⊞).
 *   2. open an asset   → a transparent, ad-bordered window over the scene
 *      (glass shows through; the ad border's house fallback is non-blank).
 *   3. open three      → all three data-workspace-window nodes coexist AND the
 *      moving scene is sampled VISIBLE in the gap beside them.
 *
 * RUN: belongs to the `ams-real` Playwright project (real SPA via vite
 * preview). When AMS_APP_URL is unset + no server boots, the project skips
 * cleanly (RULE 3). Added to ams-real testMatch + excluded from chromium
 * testIgnore in playwright.config.ts (additive).
 */

import { expect, test, type Page } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";
import { assertSceneVisible, assertWindowOpen } from "./_ams/visible";

/** The default authed route (App.tsx: "/" → ResearchWorkstation). */
const DEFAULT_ROUTE = "/";

/** Open the launcher (the single non-workflow rail affordance). */
async function openLauncher(page: Page): Promise<void> {
  await page.getByRole("button", { name: "More" }).first().click();
  // The launcher modal is a role=dialog labelled "More".
  await expect(page.getByRole("dialog", { name: "More" })).toBeVisible();
}

test.describe("AMS-v2 SPR-04 — windows are the default interaction", () => {
  // ── Proof 1 ────────────────────────────────────────────────────────────────
  // The DEFAULT product activation opens a sub-action window over the scene —
  // no buried ⊞ button. This is the inversion the operator asked for.
  test("clicking a product opens a sub-action window by default", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await openLauncher(page);
    await page.getByRole("button", { name: /open research workflow in a window/i }).first().click();
    // A floating [role=dialog][data-window-mode] window frame is on screen.
    await assertWindowOpen(page);
    // It is the sub-action page (lists the workflow's sub-actions).
    await expect(page.locator("[data-subaction-list]").first()).toBeVisible();
  });

  // ── Proof 2 ────────────────────────────────────────────────────────────────
  // Opening a within-contract ASSET surface (the Library shelf) spawns a
  // transparent, ad-bordered window over the scene. The window body is glass
  // (the scene shows through); with no parent-supplied ad fills every edge
  // resolves to the HOUSE fallback, so the border is useful, never blank.
  test("opening an asset spawns a transparent ad-bordered window over the scene", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await openLauncher(page);
    // The Library deep-mode row carries the ⊞ open-in-window affordance.
    await page.getByRole("button", { name: "Open Library in a window" }).first().click();
    await assertWindowOpen(page);

    const win = page.locator("[data-windows-layer] [data-workspace-window]").first();
    await expect(win).toBeVisible();
    // The four-edge ad border is present (WindowAdBorder, data-window-ad-border).
    await expect(page.locator("[data-windows-layer] [data-window-ad-border]").first()).toBeVisible();
    // With no parent-supplied buyer, an edge resolves to the HOUSE fallback — a
    // useful "Recommended reading" card, NEVER a blank edge (HouseSlot via
    // AdBorder, aria-label="Recommended reading").
    await expect(
      page.locator('[data-windows-layer] [aria-label="Recommended reading"]').first(),
    ).toBeVisible();

    // GLASS: the scene shows THROUGH the window body. Sample a band INSIDE the
    // window's glass body (not the title bar, not the ad rails) and assert it is
    // not one flat colour — the moving mountainscape is visible behind the glass.
    const box = await win.boundingBox();
    expect(box, "window has no bounding box to sample").not.toBeNull();
    if (box) {
      const vp = page.viewportSize() ?? { width: 1280, height: 720 };
      // A small region in the upper-mid of the body (below the ~46px ad inset +
      // ~32px title bar), away from any centred content column.
      const region = {
        x: (box.x + 24) / vp.width,
        y: (box.y + 96) / vp.height,
        width: 80 / vp.width,
        height: 120 / vp.height,
      };
      await assertSceneVisible(page, region);
    }
  });

  // ── Proof 3 ────────────────────────────────────────────────────────────────
  // The operator's "multiple terminals" vision: open three products and all
  // three window frames coexist on screen, cascaded — AND the moving scene is
  // still visible in the gap beside them (not occluded). This is what makes a
  // window the DEFAULT rather than a full-page takeover.
  test("opening three products: all three windows coexist with the scene between them", async ({ page }) => {
    await loginAndGotoApp(page, DEFAULT_ROUTE);
    await openLauncher(page);
    await page.getByRole("button", { name: /open research workflow in a window/i }).first().click();
    await openLauncher(page);
    await page.getByRole("button", { name: /open read workflow in a window/i }).first().click();
    await openLauncher(page);
    await page.getByRole("button", { name: /open write workflow in a window/i }).first().click();

    const wins = page.locator("[data-windows-layer] [data-workspace-window]");
    await expect(wins).toHaveCount(3);
    for (let i = 0; i < 3; i++) await expect(wins.nth(i)).toBeVisible();

    // The scene is sampled VISIBLE to the RIGHT of the cascaded windows (they
    // float top-left, ≤ x≈872px / 0.68; this band is right of all three),
    // proving the windows float OVER the scene rather than replacing it.
    await assertSceneVisible(page, { x: 0.76, y: 0.32, width: 0.12, height: 0.28 });

    // Capture the proof artifact: three transparent windows cascaded over the
    // moving scene — the operator's "multiple terminals" vision, made visible.
    // This is the human-auditable companion to the pixel/DOM assertions above.
    await page.screenshot({
      path: "e2e/_ams/.artifacts/windows-default-three-coexist.png",
    });
  });
});
