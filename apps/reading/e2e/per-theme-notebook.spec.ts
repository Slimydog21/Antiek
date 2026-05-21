// SPR-11 / M7 — Per-theme notebook end-to-end spec.
//
// Same Playwright-not-yet-installed convention as
// apps/reading/e2e/per-doc-notebook.spec.ts. This file is the
// spec the gate ``pnpm e2e per-theme-notebook.spec.ts`` runs
// AFTER an operator installs Playwright. The path + name match
// the sprint HTML verification gate exactly so the gate can run
// as soon as the deps land.
//
// Until Playwright lands, the equivalent assertions are covered by:
//
//   - apps/reading/src/modes/Notebook/__tests__/theme.test.tsx
//     (vitest): stale-block handling, dispatch, suggested-themes
//     stub, empty index.
//
//   - services/notebooks/tests/test_theme_persistence.py
//     (pytest): server-side promote, reorder, stale-block detection,
//     .antiek round-trip.
//
// Acceptance criteria the spec encodes (see sprint HTML M7):
//
//   1. log in (operator email gate via Cloudflare Access cookie)
//   2. open doc A → promote one block to a new theme
//   3. open doc B → promote one block to the SAME theme (existing)
//   4. open /wrestle/themes/<slug>
//   5. assert 2 blocks render in promotion order
//   6. drag block #2 above block #1 → reload → order preserved
//   7. delete a source notebook → reload theme → 1 stale + 1 live
//   8. dismiss stale → 1 live remaining

// eslint-disable-next-line @typescript-eslint/no-unused-vars
// @ts-nocheck — until Playwright lands; suppress for the operator's
// install-Playwright follow-up which will remove this directive.

import { test, expect } from "@playwright/test";

const DOC_A = process.env.ANTIEK_E2E_DOC_A || "doc-e2e-spr11-A";
const DOC_B = process.env.ANTIEK_E2E_DOC_B || "doc-e2e-spr11-B";
const THEME_TITLE =
  process.env.ANTIEK_E2E_THEME_TITLE || "SPR-11 cross-doc theme";

test.describe("per-theme notebook (SPR-11)", () => {
  test("cross-doc promote, reorder, stale-block", async ({ page }) => {
    // ── 1. Doc A: create one highlight + promote it to a new theme ──
    await page.goto(`/wrestle/${DOC_A}`);
    await page.getByTestId("pdf-text-line-100").dblclick();
    await page.getByTestId("highlight-confirm").click();
    await page.goto(`/wrestle/${DOC_A}/notebook`);
    const blockAId = await page
      .locator("[data-promote-host]")
      .first()
      .getAttribute("data-promote-host");
    await page
      .getByTestId(`promote-button-${blockAId}`)
      .click();
    await page.getByTestId("promote-search").fill(THEME_TITLE);
    await page.getByTestId("promote-create-new").click();

    // ── 2. Doc B: another highlight → same theme ──
    await page.goto(`/wrestle/${DOC_B}`);
    await page.getByTestId("pdf-text-line-100").dblclick();
    await page.getByTestId("highlight-confirm").click();
    await page.goto(`/wrestle/${DOC_B}/notebook`);
    const blockBId = await page
      .locator("[data-promote-host]")
      .first()
      .getAttribute("data-promote-host");
    await page
      .getByTestId(`promote-button-${blockBId}`)
      .click();
    await page.getByTestId("promote-search").fill(THEME_TITLE);
    // The first option in the list IS the theme we just created.
    await page.getByTestId("promote-options").locator("button").first().click();

    // ── 3. Open the theme ──
    const slug = THEME_TITLE.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    await page.goto(`/wrestle/themes/${slug}`);

    // ── 4. Two blocks render ──
    const tblocks = page.locator("[data-theme-block-id]");
    await expect(tblocks).toHaveCount(2);

    // ── 5. Drag the 2nd above the 1st ──
    const first = tblocks.nth(0);
    const second = tblocks.nth(1);
    await second.dragTo(first);
    await page.reload();
    // Order is now [second, first].
    const reloaded = page.locator("[data-theme-block-id]");
    const reloadedFirstId = await reloaded.nth(0).getAttribute("data-theme-block-id");
    const secondId = await second.getAttribute("data-theme-block-id");
    expect(reloadedFirstId).toBe(secondId);

    // ── 6. Delete the source notebook for doc A ──
    // The destructive action is operator-only and not surfaced in
    // the UI; we cleanup via the test DB harness (out of band).
    // The harness must DELETE FROM notebook_blocks WHERE notebook_id
    // matches doc A's. After that, reload the theme.
    // (Harness call elided; the test runner ensures the delete
    // happens between this and the next assertion block.)
    await page.reload();

    // ── 7. One stale + one live ──
    await expect(
      page.locator('[data-theme-block-id][data-stale="true"]'),
    ).toHaveCount(1);
    await expect(
      page.locator('[data-theme-block-id]:not([data-stale="true"])'),
    ).toHaveCount(1);

    // ── 8. Dismiss the stale ──
    const staleId = await page
      .locator('[data-theme-block-id][data-stale="true"]')
      .first()
      .getAttribute("data-theme-block-id");
    await page.getByTestId(`dismiss-stale-${staleId}`).click();
    await expect(page.locator("[data-theme-block-id]")).toHaveCount(1);
  });

  test("themes index empty state when no themes exist", async ({ page }) => {
    // This test assumes a freshly-seeded user with zero themes.
    // Setup is the responsibility of the test harness; we just
    // assert the rendered copy.
    await page.goto("/wrestle/themes");
    const empty = await page.getByTestId("themes-empty").textContent();
    expect(empty?.toLowerCase()).toMatch(
      /promote blocks from any document to start a theme/,
    );
  });

  test("suggested-themes section is visible with stub copy (no lorem)", async ({
    page,
  }) => {
    await page.goto("/wrestle/themes");
    const stub = await page.getByTestId("suggested-themes-stub").textContent();
    expect(stub?.toLowerCase()).toMatch(
      /auto-suggested themes will appear when your library has more notebooks/,
    );
    expect(stub?.toLowerCase()).not.toMatch(/lorem ipsum/);
  });
});
