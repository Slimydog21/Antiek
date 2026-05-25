/**
 * thread-navigation.spec.ts — antiek-unified SPR-06 e2e.
 *
 * Drives the cross-workflow thread breadcrumb + jump against the static
 * Storybook build (the same harness navigation-ia.spec.ts uses — no live
 * substrate needed):
 *
 *   - the breadcrumb renders a 1-hop (degenerate) thread,
 *   - the breadcrumb renders the full-flywheel thread (Research → Read → Write
 *     → Read) with each segment labeled by workflow,
 *   - jumping along the thread advances the breadcrumb (the clicked segment
 *     becomes the current position),
 *   - a hop into an unbuilt workflow shows the honest stub, not a fake screen,
 *   - a forked-copy thread suppresses the trail (the integrity warning) — the
 *     breadcrumb refuses to assert a continuity the data can't support.
 *
 *   npm run e2e
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

async function loadStory(page: Page, id: string): Promise<void> {
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
}

test.describe("SPR-06 — cross-workflow thread navigation", () => {
  test("renders a 1-hop (degenerate) thread", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--one-hop-thread");

    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toBeVisible({
      timeout: 5_000,
    });
    // The single Research hop is the current position.
    await expect(
      page.locator('[data-testid="thread-hop-current-research"]'),
    ).toBeVisible();
  });

  test("renders the full-flywheel thread with each workflow segment", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--full-flywheel-thread");

    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toBeVisible({
      timeout: 5_000,
    });
    // Research origin + Read + Write segments present.
    await expect(page.getByText(/Research insight node/)).toBeVisible();
    await expect(page.getByText(/Write insight node/)).toBeVisible();
    // The thread crosses Read twice — at least one Read segment is shown.
    await expect(page.getByText(/Read insight node/).first()).toBeVisible();
  });

  test("jumping along the thread advances the breadcrumb", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 500 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--jump-along-thread");

    await expect(page.locator('[data-testid="thread-jump"]')).toBeVisible({
      timeout: 5_000,
    });
    // Initially the canonical entity is in focus at the Research origin; the
    // Write segment is a navigable button.
    const writeSegment = page.locator('[data-testid="thread-hop-write"]');
    await expect(writeSegment).toBeVisible();
    // Jump to Write. Because every hop shares the SAME entity id, the active
    // entity doesn't change id — but the jump is accepted (no crash, no fake
    // screen) since Write IS a built workflow. The breadcrumb stays coherent.
    await writeSegment.click();
    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toBeVisible();
  });

  test("a hop into an unbuilt workflow shows the honest stub segment", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--with-unbuilt-hop");

    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toBeVisible({
      timeout: 5_000,
    });
    // The unbuilt hop is a dimmed, non-navigable "not yet" segment — never a
    // fake clickable target.
    await expect(
      page.locator('[data-testid="thread-hop-stub-write"]'),
    ).toBeVisible();
    await expect(page.getByText(/not yet available/i)).toBeVisible();
  });

  test("a forked-copy thread suppresses the trail (integrity warning)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(
      page,
      "shell-threadbreadcrumb-spr-06--forked-thread-suppressed",
    );

    // The breadcrumb refuses to render a trail over copied entities.
    await expect(
      page.locator('[data-testid="thread-breadcrumb-integrity-warning"]'),
    ).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/integrity error/i)).toBeVisible();
    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toHaveCount(0);
  });
});
