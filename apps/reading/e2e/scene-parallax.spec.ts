/**
 * scene-parallax.spec.ts — the peaks' anti-nausea ceiling, measured in
 * rendered pixels (design audit 2026-09-23, blocker B1).
 *
 * peaks.ts documents MAX_PARALLAX_PX = 8: sweeping the pointer across the
 * whole viewport may move the nearest ridge by at most ±8px (16px of travel).
 * On 0ac6470 the shift was added in 0-100 viewBox units, so the near ridge
 * travelled 8% of the viewport height each way (134-139px at 900px high)
 * while the constant-only unit test stayed green. This gate reads the ridge's
 * rendered bounding box, so it measures what a reader's eyes see.
 *
 * The two bounds make it non-vacuous in both directions: travel above the
 * ceiling fails (the unit bug), and travel near zero fails too (parallax
 * silently disconnected). Slack covers the ambient drift (DRIFT.peaks, ±1.2px
 * over a 47s period, so well under 1px across one sweep).
 *
 * Runs in the `chromium` (Storybook) project on the real composed AppShell,
 * with motion ON: under reduced motion the scene freezes and there is nothing
 * to measure.
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const APPSHELL_STORY = "navigation-appshell--with-project-tree";
const MAX_PARALLAX_PX = 8; // peaks.ts — the documented ceiling under test
const DRIFT_SLACK_PX = 1;

test.use({ contextOptions: { reducedMotion: "no-preference" } });

/** Rendered top edge of each ridge band (far → near), in CSS px. */
async function ridgeTops(page: Page): Promise<number[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid="procedural-sky"] path')).map(
      (p) => p.getBoundingClientRect().top,
    ),
  );
}

/** Wait until the eased parallax has settled (two reads 150ms apart agree). */
async function settledTops(page: Page): Promise<number[]> {
  let prev = await ridgeTops(page);
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(150);
    const next = await ridgeTops(page);
    if (next.every((v, k) => Math.abs(v - prev[k]) < 0.05)) return next;
    prev = next;
  }
  return prev;
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`near ridge travels at most 2 x ${MAX_PARALLAX_PX}px for a full pointer sweep at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(`${STORYBOOK_URL}/iframe.html?args=&id=${APPSHELL_STORY}&viewMode=story`, {
      waitUntil: "domcontentloaded",
    });
    const root = page.locator('[data-testid="scene-root"]');
    await expect(root).toHaveAttribute("data-scene-frozen", "false", { timeout: 10_000 });
    await expect(page.locator('[data-testid="procedural-sky"] path')).toHaveCount(3);

    await page.mouse.move(viewport.width / 2, 1);
    const top = await settledTops(page);
    await page.mouse.move(viewport.width / 2, viewport.height - 1);
    const bottom = await settledTops(page);

    const travel = bottom.map((v, i) => Math.abs(v - top[i]));
    const [far, , near] = travel;
    test.info().annotations.push({
      type: "ridge-travel-px",
      description: JSON.stringify({ viewport, far, mid: travel[1], near }),
    });

    // The ceiling: ±8px of pointer shift, i.e. 16px of travel, in real px.
    expect(near, `near ridge travel ${near.toFixed(1)}px`).toBeLessThanOrEqual(
      2 * MAX_PARALLAX_PX + DRIFT_SLACK_PX,
    );
    // Non-vacuous: the parallax is still connected and reads as depth.
    expect(near).toBeGreaterThan(2 * MAX_PARALLAX_PX * 0.8);
    expect(far).toBeLessThan(near);
  });
}
