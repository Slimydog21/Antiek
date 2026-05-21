// SPR-08 / M8 — Per-document notebook end-to-end spec.
//
// Playwright is NOT yet installed in apps/reading (the package.json
// has no @playwright/test dependency at SPR-08 closeout). This file
// is the spec the gate ``pnpm e2e per-doc-notebook.spec.ts`` runs
// AFTER an operator installs Playwright. The path + name match the
// sprint HTML verification gate exactly so the gate can run as soon
// as the deps land.
//
// Until Playwright lands, the equivalent assertions are covered by:
//
//   - apps/reading/src/modes/Notebook/__tests__/notebook.test.tsx
//     (vitest + @testing-library/react): block dispatch, demote
//     round-trip, no-authoring guard.
//
//   - services/notebooks/tests/test_auto_populate.py
//     (pytest): server-side idempotency, demote round-trip,
//     reward join, block→event link.
//
// Acceptance criteria the spec encodes (see sprint HTML M8):
//
//   1. log in (operator email gate via Cloudflare Access cookie)
//   2. open a document at /wrestle/<documentId>
//   3. make 3 highlights + 1 voice note
//   4. open /wrestle/<documentId>/notebook
//   5. assert 4 blocks render (3 highlight_card + 1 voice_block)
//   6. demote 1 block
//   7. reload
//   8. assert 3 blocks render in main flow, 1 in Demoted (1) zone
//   9. expand Demoted → restore → reload → assert 4 in main flow

// eslint-disable-next-line @typescript-eslint/no-unused-vars
// @ts-nocheck — until Playwright lands; suppress for the operator's
// install-Playwright follow-up which will remove this directive.

import { test, expect } from "@playwright/test";

const DOC_ID = process.env.ANTIEK_E2E_DOC_ID || "doc-e2e-spr08-test";

test.describe("per-doc notebook (SPR-08)", () => {
  test("auto-populate, demote, reload round-trip", async ({ page }) => {
    // 1. Log in via Cloudflare Access (handled by global setup;
    //    this block assumes the storageState already carries the
    //    cookie).
    await page.goto(`/wrestle/${DOC_ID}`);

    // 2 + 3. Make 3 highlights + 1 voice note. The reading surface
    // exposes highlights via the gutter handle; voice note via the
    // SPR-05 capture button. The selectors below match the existing
    // PdfViewer + InterviewVoiceCapture component test ids.
    for (let i = 0; i < 3; i++) {
      await page.getByTestId(`pdf-text-line-${100 + i}`).dblclick();
      await page.getByTestId("highlight-confirm").click();
    }
    await page.getByTestId("voice-capture-start").click();
    await page.waitForTimeout(2000);
    await page.getByTestId("voice-capture-stop").click();

    // 4. Open the per-doc notebook.
    await page.goto(`/wrestle/${DOC_ID}/notebook`);

    // 5. Four blocks render.
    const blocks = page.locator("[data-block-id]");
    await expect(blocks).toHaveCount(4);
    await expect(
      page.locator('[data-block-type="highlight_card"]'),
    ).toHaveCount(3);
    await expect(
      page.locator('[data-block-type="voice_block"]'),
    ).toHaveCount(1);

    // 6. Demote one.
    const firstBlock = blocks.first();
    const firstId = await firstBlock.getAttribute("data-block-id");
    await firstBlock.hover();
    await page.getByTestId(`demote-button-${firstId}`).click();

    // 7. Reload.
    await page.reload();

    // 8. 3 in main flow, 1 in Demoted.
    await expect(page.locator("[data-block-id]")).toHaveCount(3);
    const zone = page.getByTestId("demote-zone");
    await expect(zone).toBeVisible();
    await expect(page.getByTestId("demote-zone-toggle")).toContainText(
      /Demoted \(1\)/,
    );

    // 9. Expand + restore + reload.
    await page.getByTestId("demote-zone-toggle").click();
    await page.getByTestId(`demote-button-${firstId}`).click();
    await page.reload();
    await expect(page.locator("[data-block-id]")).toHaveCount(4);
  });

  test("no '+ new block' affordance anywhere on the notebook surface", async ({
    page,
  }) => {
    await page.goto(`/wrestle/${DOC_ID}/notebook`);
    // Scan visible text. ``screen-reader-only`` content with these
    // strings would also fail — appropriate, since the affordance
    // must be absent both visually and from accessibility tree.
    const body = await page.locator("body").textContent();
    expect(body?.toLowerCase()).not.toMatch(/\+ new block/);
    expect(body?.toLowerCase()).not.toMatch(/create block/);
    expect(body?.toLowerCase()).not.toMatch(/new block/);
  });
});
