/**
 * feel-experience-matrix.spec.ts — FEEL-S6 consolidated programme proof.
 * Re-asserts the highest-signal criteria; detailed proofs live in sibling specs.
 */
import { expect, test } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

test.describe("PostHog Feel — experience matrix", () => {
  test("F3: three launcher windows cascade (title bars ≥18px apart)", async ({
    page,
  }) => {
    await loginAndGotoApp(page, "/");
    await page.getByRole("button", { name: "More" }).first().click();
    await page
      .getByRole("button", { name: /open research workflow in a window/i })
      .first()
      .click();
    await page.getByRole("button", { name: "More" }).first().click();
    await page
      .getByRole("button", { name: /open read workflow in a window/i })
      .first()
      .click();
    await page.getByRole("button", { name: "More" }).first().click();
    await page
      .getByRole("button", { name: /open write workflow in a window/i })
      .first()
      .click();

    const bars = page.locator("[data-window-titlebar]");
    await expect(bars).toHaveCount(3);
    const boxes = await bars.evaluateAll((nodes) =>
      nodes.map((n) => {
        const r = n.getBoundingClientRect();
        return { x: r.x, y: r.y };
      }),
    );
    expect(Math.abs(boxes[2].x - boxes[0].x)).toBeGreaterThanOrEqual(18);
    expect(Math.abs(boxes[2].y - boxes[0].y)).toBeGreaterThanOrEqual(18);
  });

  test("F6: no PostHog hedgehog assets in built shell markup sample", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const app = readFileSync(
      resolve(import.meta.dirname, "../src/App.tsx"),
      "utf8",
    );
    expect(app.toLowerCase()).not.toContain("hedgehog");
    expect(app).not.toContain("posthog.com");
  });
});