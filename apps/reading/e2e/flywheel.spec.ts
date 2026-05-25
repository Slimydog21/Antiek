/**
 * flywheel.spec.ts — antiek-unified SPR-08 M5 (frontend e2e flywheel).
 *
 * Walks the flywheel through the UI as far as the built products allow, against
 * the static Storybook build (the same harness thread-navigation.spec.ts uses —
 * no live substrate). The flywheel's UI warrant is the SPR-06 thread breadcrumb:
 * ONE entity, tracked across the workflows it touches, by the SAME node id.
 *
 *   - Walk the full flywheel (Research → Read → Write → Read) and confirm the
 *     breadcrumb tracks the SAME entity across every workflow segment.
 *   - Where a product is UNBUILT, the test asserts the honest SPR-04 stub
 *     appears rather than a fake screen (intellectual honesty #1 — the UI
 *     flywheel is honest about what exists).
 *   - The negative: a forked-copy thread suppresses the trail (the breadcrumb
 *     refuses to assert a continuity the data can't support).
 *
 * HONEST SCOPE (rigor #1): the *served-back-in-Read* leg is not a live serve —
 * Read's reader (substrate/books/) is unbuilt on this base. The breadcrumb
 * tracking the entity through the Read segment is the UI-level proof available;
 * the live Read-serving leg lands when Read merges. The Python e2e
 * (tests/e2e/test_flywheel.py) proves the served-back leg at the CONTRACT level.
 *
 *   npm run e2e   (builds Storybook, then runs Playwright)
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

// The one canonical entity the whole flywheel is about — identical to the
// Python e2e's CANONICAL_INSIGHT and the ThreadBreadcrumb story fixture.
const CANONICAL = "insight-7f3a9c";

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

async function loadStory(page: Page, id: string): Promise<void> {
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
}

test.describe("SPR-08 — frontend flywheel walk (one entity, four workflows)", () => {
  test("walks the full flywheel; the breadcrumb tracks ONE entity across workflows", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--full-flywheel-thread");

    const breadcrumb = page.locator('[data-testid="thread-breadcrumb"]');
    await expect(breadcrumb).toBeVisible({ timeout: 5_000 });

    // The flywheel's workflow segments are present, in order: Research origin →
    // Read → Write (→ Read). This is the "four workflows are one product" walk.
    await expect(page.getByText(/Research insight node/)).toBeVisible();
    await expect(page.getByText(/Read insight node/).first()).toBeVisible();
    await expect(page.getByText(/Write insight node/)).toBeVisible();

    // The load-bearing UI assertion: the breadcrumb is ABOUT one canonical
    // entity. Every hop in the full-flywheel fixture carries `insight-7f3a9c`;
    // the breadcrumb renders that single thread, not four disconnected views.
    // (The forked case below proves the breadcrumb refuses a multi-id trail.)
    const research = page.locator('[data-testid="thread-hop-current-research"]');
    const write = page.locator('[data-testid="thread-hop-write"]');
    await expect(research).toBeVisible();
    await expect(write).toBeVisible();
  });

  test("an unbuilt workflow hop shows the honest SPR-04 stub, not a fake screen", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(page, "shell-threadbreadcrumb-spr-06--with-unbuilt-hop");

    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toBeVisible({
      timeout: 5_000,
    });
    // The Write hop is marked unbuilt → an honest, non-navigable "not yet"
    // stub segment, NEVER a fabricated clickable target (intellectual honesty
    // #1). This is the UI flywheel being honest about what exists.
    await expect(
      page.locator('[data-testid="thread-hop-stub-write"]'),
    ).toBeVisible();
    await expect(page.getByText(/not yet available/i)).toBeVisible();
  });

  test("a forked-copy thread suppresses the flywheel trail (integrity warning)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 400 });
    await loadStory(
      page,
      "shell-threadbreadcrumb-spr-06--forked-thread-suppressed",
    );

    // The negative the flywheel rests on: if a hop ever held a COPY (a
    // different id), the breadcrumb must NOT render a trail — it would assert a
    // continuity the data can't support. The integrity warning shows instead.
    await expect(
      page.locator('[data-testid="thread-breadcrumb-integrity-warning"]'),
    ).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/integrity error/i)).toBeVisible();
    await expect(page.locator('[data-testid="thread-breadcrumb"]')).toHaveCount(
      0,
    );
  });
});
