/**
 * feel-focus-ring.spec.ts — FEEL-S5 keyboard focus visibility.
 */
import { expect, test } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

test.describe("FEEL-S5 — focus ring", () => {
  test("Tab reaches a Lemon button with visible focus", async ({ page }) => {
    await page.goto(
      `${STORYBOOK_URL}/iframe.html?args=&id=design-primitives-showcase--showcase&viewMode=story`,
      { waitUntil: "domcontentloaded" },
    );
    await page.keyboard.press("Tab");
    const active = page.locator(":focus");
    await expect(active).toBeVisible({ timeout: 5_000 });
    const outlineWidth = await active.evaluate(
      (el) => getComputedStyle(el).outlineWidth,
    );
    const boxShadow = await active.evaluate(
      (el) => getComputedStyle(el).boxShadow,
    );
    const hasRing =
      outlineWidth !== "0px" || (boxShadow && boxShadow !== "none");
    expect(hasRing).toBe(true);
  });
});