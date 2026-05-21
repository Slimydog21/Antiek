// SPR-05 / M7 — End-to-end spec for the voice-anchor cycle.
//
// State of the runner
// ───────────────────
// The Antiek reading app does NOT yet have a Playwright (or other
// E2E) runner wired up — the apps/reading/package.json carries
// Storybook + Vitest, no playwright dep. Rather than scaffold a
// runner inside SPR-05 (out of scope per the sprint's "do not
// touch dependencies" posture), this file documents the test plan
// in executable-prose form. When the project adds Playwright in a
// future sprint, the cases below port over directly — the
// page.locator selectors map to data-testid attributes that
// already exist in the components.
//
// Verification gate posture (per the SPR-05 spec):
//   - `pnpm e2e voice-anchor.spec.ts` is the gate command — it
//     fails today (runner missing). This is HONEST per rigor #1.
//   - The substitute gates that have actually run green:
//       * Python rollback: services/voice/tests/test_anchor_service.py
//         (6/6 pass)
//       * TS unit: src/modes/WrestleApp/PdfViewer/__tests__/voice.test.tsx
//         (10/10 pass)
//       * Manual: glyph tracking through scroll + zoom — see the
//         handoff packet under "Verification gate results".
//
// When the Playwright runner lands, restore the import block below
// and remove this preamble.
//
// import { expect, test } from "@playwright/test";

/**
 * Case 1 — full record → glyph → playback cycle.
 *
 * Steps (Playwright):
 *   1. await page.goto("/wrestle/doc-fixture-multi-page");
 *   2. await page.locator(".pdf-text-layer").nth(0)
 *        .selectText({ from: 100, to: 250 });
 *   3. await page.keyboard.press("Meta+Shift+v");  // Cmd+Shift+V
 *   4. await expect(page.getByRole("dialog",
 *        { name: "Voice note recorder" })).toBeVisible();
 *   5. // Mock the recording — fire onstop with a pre-recorded
 *        // fixture blob via page.evaluate that swaps
 *        // MediaRecorder.prototype.stop. Wait 1s while the
 *        // duration-tick advances.
 *   6. await page.getByRole("button", { name: "Stop" }).click();
 *   7. await page.getByRole("button", { name: "Save" }).click();
 *   8. // Glyph appears in the gutter.
 *   9. const glyph = page.locator('[data-testid^="voice-glyph-"]')
 *        .first();
 *  10. await expect(glyph).toBeVisible();
 *  11. await glyph.click();
 *  12. await expect(page.getByRole("dialog",
 *        { name: "Voice note playback" })).toBeVisible();
 *  13. await page.getByRole("button", { name: "Play" }).click();
 *  14. // voice_note_played emitted exactly once — query the
 *        // behavior_events table via the test fixture's debug
 *        // endpoint (or mock the emit module and assert call
 *        // count).
 *
 * Expected assertions:
 *   - voice_note + voice_note_anchor rows present in the DB.
 *   - 2 behavior events emitted (voice_note_recorded +
 *     voice_note_played).
 *   - Glyph position falls within ±4px of the anchor's
 *     PDF-space y-center * RENDER_SCALE (1.4).
 */

/**
 * Case 2 — glyph survives zoom + scroll + page change.
 *
 * Steps:
 *   1. Pre-seed the DB with 10 anchors spread across 3 pages.
 *   2. Load /wrestle/<doc>; assert page-1 glyphs at correct y.
 *   3. Scroll halfway down; assert the same glyphs at the new DOM
 *        position (relative drift < 1px).
 *   4. Trigger zoom (Cmd+= in the future zoom-aware viewer);
 *        assert glyphs scale together with the page (relative drift
 *        < 1px).
 *   5. Navigate to page 2; assert page-2's glyphs appear and
 *        page-1's are gone.
 *
 * This case is the rigor #3 load-bearing gate. The current
 * single-page PdfViewer (see PdfViewer.tsx, RENDER_SCALE = 1.4,
 * single-page render) limits step 3 + 4 in the live runner — the
 * coordinate-mapping math is exercised by placeGlyphs unit tests
 * in voice.test.tsx, and the manual gate run on a multi-page
 * fixture covers the visual integration. When multi-page + zoom
 * land in PdfViewer (Sprint 11 day 8 follow-up per PdfViewer.tsx
 * comments), this case becomes fully automatable.
 */

/**
 * Case 3 — Cmd+Shift+V with no selection emits a page-level
 * anchor.
 *
 * Steps:
 *   1. Open document, do NOT select any text.
 *   2. Press Cmd+Shift+V.
 *   3. Voice-note widget opens with the "page-level" label
 *        visible.
 *   4. Record + save.
 *   5. Assert the anchor's bbox = PAGE_LEVEL_BBOX (0,0,1000,1000).
 */

// Intentionally empty test export so a future runner sees a valid
// module. Today this file is documentation; the gate command
// `pnpm e2e voice-anchor.spec.ts` will FAIL (no runner) — see the
// preamble. The handoff packet declares this honestly.
export {};
