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
    // The showcase mounts asynchronously AFTER `load`: measured at this
    // commit, `domcontentloaded` and `load` both see only 3 buttons while the
    // settled story has 23. Tabbing at either point leaves document.body
    // focused, so `:focus` matches nothing and the ring assertion never runs.
    // Wait on the condition the test actually needs -- focusable content
    // present -- rather than on a load event that does not imply it.
    await page.waitForFunction(
      () => document.querySelectorAll("button").length > 5,
      null,
      { timeout: 10_000 },
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