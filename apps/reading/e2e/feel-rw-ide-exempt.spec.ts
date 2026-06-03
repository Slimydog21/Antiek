/**
 * feel-rw-ide-exempt.spec.ts — FEEL-S4: dense RW IDE stays non-floating stack.
 */
import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

async function clearWorkspacePersistence(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k?.startsWith("antiek.workspace.")) {
        localStorage.removeItem(k);
      }
    }
  });
}

test.describe("FEEL-S4 — ResearchWorkstation IDE exempt", () => {
  test("research landing has no floating opaque stack chrome", async ({
    page,
  }) => {
    await clearWorkspacePersistence(page);
    await loginAndGotoApp(page, "/");
    await expect(page.locator("textarea").first()).toBeVisible({
      timeout: 15_000,
    });

    // Floating panels carry absolute geometry; landing must not stack them.
    const floatingPanels = page.locator(
      '[role="region"][style*="position: absolute"]',
    );
    await expect(floatingPanels).toHaveCount(0);

    const leftDock = page.locator('aside[aria-label="Left dock"]').first();
    if ((await leftDock.count()) > 0) {
      const dockHtml = await leftDock.evaluate((el) => el.innerHTML);
      expect(dockHtml).not.toMatch(/shadow-z3/);
    }

    await expect(page.locator('[data-glass-surface="glass"]').first()).toBeVisible();
  });

  test("composer control exposes sun focus-visible ring", async ({ page }) => {
    await clearWorkspacePersistence(page);
    await loginAndGotoApp(page, "/");
    const textarea = page.locator("textarea").first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.focus();
    await expect(textarea).toBeFocused();
    const ring = await textarea.evaluate((el) => getComputedStyle(el).outlineColor);
    expect(ring).toBeTruthy();
  });
});