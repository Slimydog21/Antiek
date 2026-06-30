/**
 * feel-focus-ring.spec.ts — FEEL-S5 keyboard focus visibility.
 */
import { expect, test } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

async function resolvedSunRgb(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = getComputedStyle(document.documentElement)
      .getPropertyValue("--sun")
      .trim();
    document.body.appendChild(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  });
}

test.describe("FEEL-S5 — focus ring", () => {
  test("Tab reaches a Lemon button with visible focus", async ({ page }) => {
    await page.goto(
      `${STORYBOOK_URL}/iframe.html?args=&id=design-primitives-showcase--showcase&viewMode=story`,
      { waitUntil: "domcontentloaded" },
    );
    const target = page.getByRole("button", { name: "primary · sm" });
    await expect(target).toBeVisible();

    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("Tab");
      if (await target.evaluate((el) => el === document.activeElement)) break;
    }

    await expect(target).toBeFocused();
    const sun = await resolvedSunRgb(page);
    const boxShadow = await target.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(boxShadow).toContain(sun);
  });
});
