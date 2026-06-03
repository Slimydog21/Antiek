/**
 * feel-panels-cascade.spec.ts — FEEL-S2 panel stack harness.
 *
 * Uses the Workspace / Demo Storybook harness (`data-testid=feel-three-stack`)
 * to open three floating panels with a visible cascade. Honest scope: this
 * does not claim the production Research route opens three panels by default.
 *
 * Runs under the default `chromium` project (`npm run e2e`) where Storybook
 * :6006 is booted. Not in `e2e:ams` until FEEL-S6 adds a consolidated gate.
 */

import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

async function loadWorkspaceDemo(page: Page): Promise<void> {
  await page.goto(
    `${STORYBOOK_URL}/iframe.html?args=&id=workspace-demo--scene&viewMode=story`,
    { waitUntil: "domcontentloaded" },
  );
}

test.describe("FEEL-S2 — floating panel cascade", () => {
  test("three floating panels have separated corners (Storybook harness)", async ({
    page,
  }) => {
    await loadWorkspaceDemo(page);
    await page.getByTestId("feel-three-stack").click();

    const regions = page.locator('[role="region"]');
    await expect(regions).toHaveCount(3, { timeout: 8_000 });

    const boxes = await regions.evaluateAll((nodes) =>
      nodes.map((n) => {
        const r = n.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y) };
      }),
    );

    const uniq = new Set(boxes.map((b) => `${b.x},${b.y}`));
    expect(uniq.size).toBe(3);

    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const dx = Math.abs(boxes[i].x - boxes[j].x);
        const dy = Math.abs(boxes[i].y - boxes[j].y);
        expect(dx + dy).toBeGreaterThanOrEqual(20);
      }
    }

    const shadowRank = (cls: string) => {
      if (cls.includes("shadow-z3")) return 3;
      if (cls.includes("shadow-z2")) return 2;
      if (cls.includes("shadow-z1")) return 1;
      return 0;
    };

    const stacks = await regions.evaluateAll((nodes) =>
      nodes.map((n) => ({
        z: Number.parseInt(getComputedStyle(n).zIndex, 10) || 0,
        rank: shadowRank(n.className),
      })),
    );
    stacks.sort((a, b) => a.z - b.z);
    expect(stacks[0].rank).toBeLessThan(stacks[stacks.length - 1].rank);
  });
});