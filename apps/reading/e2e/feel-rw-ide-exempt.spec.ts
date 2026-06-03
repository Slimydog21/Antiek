/**
 * feel-rw-ide-exempt.spec.ts — FEEL-S4: dense RW IDE stays non-floating stack.
 */
import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

test.describe("FEEL-S4 — ResearchWorkstation IDE exempt", () => {
  test("landing dock column has no floating panel shadow-z3 tier", async ({
    page,
  }) => {
    await loginAndGotoApp(page, "/");

    const dockedRegions = page.locator(
      '[role="region"]:not([style*="position: absolute"])',
    );
    const count = await dockedRegions.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const cls = (await dockedRegions.nth(i).getAttribute("class")) ?? "";
      expect(cls).not.toMatch(/shadow-z3/);
    }
  });

  test("composer control exposes sun focus-visible ring", async ({ page }) => {
    await loginAndGotoApp(page, "/");
    const textarea = page.locator("textarea").first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.focus();
    await expect(textarea).toBeFocused();
    const ring = await textarea.evaluate((el) => getComputedStyle(el).outlineColor);
    expect(ring).toBeTruthy();
  });
});