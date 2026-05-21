// SPR-04 M6 — Playwright E2E spec for the reading-mode toggle.
//
// HONEST STATUS (2026-05-21): the repository does not yet wire
// Playwright (no playwright.config.ts in apps/reading/). This file is
// the canonical spec for the E2E gate; when the harness lands, the
// `test`/`expect` import below resolves and these tests run as-is.
//
// We use the same `@playwright/test` shape Antiek's downstream harness
// will use. Until then, `pnpm e2e reading-mode.spec.ts` simply
// reports "no Playwright config" — that's a missing-harness gate, not
// a missing-test gate. Mechanical scroll-preservation + emit + ⌘K
// behavior are covered by the vitest suite in
// src/modes/WrestleApp/__tests__/readingMode.test.tsx (which DOES
// run today).
//
// @ts-nocheck — Playwright is not in package.json yet. Strip this
// directive once @playwright/test is installed.

import { test, expect } from "@playwright/test";

test.describe("SPR-04 reading-mode toggle", () => {
  test("toggle hides NotesPanel and preserves scroll position", async ({ page }) => {
    await page.goto("/wrestle");

    // Load a fixture PDF. Path is the convention the rest of the
    // suite uses (see apps/reading/e2e/fixtures/ in a later sprint).
    await page.setInputFiles(
      'input[type="file"][accept="application/pdf"]',
      "e2e/fixtures/test.pdf",
    );

    // Wait for the PdfViewer wrapper.
    const pdf = page.getByTestId("wrestle-pdf-wrapper");
    await expect(pdf).toBeVisible();

    // Force researcher mode (existing-user shape) so we have a
    // NotesPanel to hide.
    const toggle = page.getByTestId("reading-mode-toggle");
    // Initial state is reader (new-user default in fresh contexts);
    // click to enter researcher.
    await toggle.click();
    await expect(page.getByTestId("wrestle-shell")).toHaveAttribute(
      "data-reading-mode",
      "researcher",
    );
    await expect(page.getByTestId("wrestle-notes-panel")).toBeVisible();

    // Scroll the PdfViewer wrapper to a known position.
    await pdf.evaluate((el) => {
      (el as HTMLElement).scrollTop = 512;
    });
    const scrollBefore = await pdf.evaluate(
      (el) => (el as HTMLElement).scrollTop,
    );
    expect(scrollBefore).toBe(512);

    // Toggle to reader.
    await toggle.click();
    await expect(page.getByTestId("wrestle-shell")).toHaveAttribute(
      "data-reading-mode",
      "reader",
    );
    // NotesPanel container still in DOM but display:none.
    const notes = page.getByTestId("wrestle-notes-panel");
    await expect(notes).toBeHidden();

    // Scroll preserved across the toggle (PdfViewer was not unmounted).
    const scrollAfter = await pdf.evaluate(
      (el) => (el as HTMLElement).scrollTop,
    );
    expect(scrollAfter).toBe(512);
  });

  test("Cmd+K opens AI palette; Esc closes and returns focus", async ({ page }) => {
    await page.goto("/wrestle");

    await page.keyboard.press("Meta+k");
    await expect(page.getByTestId("ai-command-palette")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("ai-command-palette")).toBeHidden();

    // Focus is back on the PdfViewer wrapper.
    const focused = await page.evaluate(() =>
      (document.activeElement as HTMLElement | null)?.getAttribute(
        "data-testid",
      ),
    );
    expect(focused).toBe("wrestle-pdf-wrapper");
  });
});
