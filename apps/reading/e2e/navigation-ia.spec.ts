/**
 * navigation-ia.spec.ts — SPR-04 milestone 7 e2e.
 *
 * Drives the reorganized four-workflow IA against the static Storybook
 * build (the same harness the smoke suite uses — no live substrate
 * needed):
 *
 *   - the rail presents EXACTLY four workflows + Search + New + a single
 *     "More" affordance (the ⊞ launcher, now in the footer),
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
    // The workflows nav region holds EXACTLY the four workflows — the ⊞
    // launcher is now the single "More" affordance in the footer, not in
    // this region. The four workflow labels must each be present via
    // their sr-only label / title.
    for (const label of ["Research", "Read", "Write", "Speak"]) {
      await expect(
        page.locator(`button[title^="${label} -"]`),
      ).toBeVisible({ timeout: 5_000 });
    }
    // Exactly four buttons in the workflows region — not five, not 37.
    await expect(workflows).toHaveCount(4);
    // ...plus a single "More" affordance outside the region.
    await expect(
      page.locator('button[title^="More -"]'),
    ).toBeVisible({ timeout: 5_000 });
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
    // Read nouns (different from Research). DocumentsIndex + Sources were
    // evicted out of the Read door into shared/More -- taxonomy.test.ts pins
    // that eviction -- and the personal meta-docs tab was added after the
    // Library. Measured from the built story, the Read subtitle is now
    // exactly "Library · Meta-docs · Notebooks". What this test exists to
    // prove is unchanged: the tree re-scopes, Read nouns != Research nouns.
    await expect(
      page.getByText("Library · Meta-docs · Notebooks"),
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
    // "Pending surfaces" is NOT asserted visible, because it cannot be.
    // WorkflowStub guards that block with `pending.length > 0`, where
    // `pending = modes.filter(m => !m.built)`, and workflowTaxonomy.ts now
    // carries ZERO `built: false` entries across all four workflows
    // (write 3, research 8, read 8, speak 6). `forceUnbuiltForStory` forces
    // the stub BRANCH but cannot populate the list, so that UI is currently
    // unreachable — dead code rather than drift.
    //
    // Asserting its ABSENCE pins that state instead of hiding it: the day a
    // mode ships as unbuilt, this fails and forces the block to be re-tested
    // properly rather than silently coming back untested.
    await expect(page.getByText("Pending surfaces")).toHaveCount(0);
  });
});
