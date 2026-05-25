/**
 * navigation-ia.spec.ts — SPR-04 milestone 7 e2e.
 *
 * Drives the reorganized four-workflow IA against the static Storybook
 * build (the same harness the smoke suite uses — no live substrate
 * needed):
 *
 *   - the rail presents EXACTLY four workflows + Search + New + ⊞,
 *   - selecting a workflow re-scopes the content-first project tree
 *     (Research nouns ≠ Read nouns),
 *   - the scene chrome renders a per-workflow action bar + tabs,
 *   - an unbuilt section shows the honest "not yet" stub, not a fake UI.
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

test.describe("SPR-04 — four-workflow navigation IA", () => {
  test("the rail presents exactly four workflows (not 37)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "shell-navrail-spr-04--four-workflow-rail");

    const workflows = page.locator('[data-testid="navrail-workflows"] button');
    // Four workflows + the ⊞ products launcher button = 5 buttons in the
    // workflows nav region. The four workflow labels must each be present
    // via their sr-only label / title.
    for (const label of ["Research", "Read", "Write", "Speak"]) {
      await expect(
        page.locator(`button[title^="${label} —"]`),
      ).toBeVisible({ timeout: 5_000 });
    }
    // Exactly five buttons in the workflows region (4 workflows + ⊞).
    await expect(workflows).toHaveCount(5);
  });

  test("the content tree re-scopes per workflow (Research nouns ≠ Read nouns)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });

    await loadStory(page, "shell-navrail-spr-04--rail-with-research-tree");
    await expect(
      page.locator('[data-testid="project-tree-research"]'),
    ).toBeVisible({ timeout: 5_000 });
    // Research nouns
    await expect(page.getByText("Investigations · Chase trees · Outcomes")).toBeVisible();

    await loadStory(page, "shell-navrail-spr-04--rail-with-read-tree");
    await expect(
      page.locator('[data-testid="project-tree-read"]'),
    ).toBeVisible({ timeout: 5_000 });
    // Read nouns (different from Research)
    await expect(
      page.getByText("Library · Documents · Notebooks · Sources"),
    ).toBeVisible();
  });

  test("the scene chrome shows a per-workflow action bar + tabs", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "shell-navrail-spr-04--research-scene-chrome");
    await expect(
      page.locator('[data-testid="scene-chrome-research"]'),
    ).toBeVisible({ timeout: 5_000 });
    // A primary verb + a tab.
    await expect(page.getByRole("button", { name: "New investigation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Workstation" })).toBeVisible();
  });

  test("an unbuilt section shows the honest 'not yet' stub", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "shell-navrail-spr-04--honest-stub");
    await expect(
      page.locator('[data-testid="workflow-stub-write"]'),
    ).toBeVisible({ timeout: 5_000 });
    // The honest copy — never a fake screen.
    await expect(page.getByText(/Not yet/i)).toBeVisible();
    await expect(page.getByText("Pending surfaces")).toBeVisible();
  });
});
