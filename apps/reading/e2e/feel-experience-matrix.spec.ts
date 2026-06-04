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
    const { readFileSync, readdirSync } = await import("node:fs");
    const { resolve, join } = await import("node:path");
    const app = readFileSync(
      resolve(import.meta.dirname, "../src/App.tsx"),
      "utf8",
    );
    expect(app.toLowerCase()).not.toContain("hedgehog");
    expect(app).not.toContain("posthog.com");

    // The mascot must not appear anywhere in shipped source — not just
    // App.tsx. The analytics lib files (posthogClient.ts / PostHog*.tsx)
    // legitimately reference the posthog.com host, so only the brand/voice
    // mascot string is asserted tree-wide here.
    const srcRoot = resolve(import.meta.dirname, "../src");
    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const p = join(dir, entry.name);
        if (entry.isDirectory()) return walk(p);
        return /\.(ts|tsx|css|md|html)$/.test(entry.name) ? [p] : [];
      });
    for (const file of walk(srcRoot)) {
      expect(
        readFileSync(file, "utf8").toLowerCase(),
        `mascot string in ${file}`,
      ).not.toContain("hedgehog");
    }
  });
});