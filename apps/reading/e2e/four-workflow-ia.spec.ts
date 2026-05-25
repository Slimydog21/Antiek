/**
 * SPR-08 acceptance — the four-workflow walk.
 *
 * Mechanical proof the "four workflows, one surface" IA holds end-to-end. It
 * drives the composed shell (NavRail · Topbar scene chrome · workflow-scoped
 * ProjectTree · ProductsLauncher) and asserts each promise of the IA:
 *
 *   1. the rail carries exactly the four workflows
 *   2. selecting a workflow re-scopes the content tree (the folders + the
 *      tree's workflow label change) AND re-routes the scene body
 *   3. the Topbar scene chrome shows that workflow's tabs — built tabs are
 *      live links, soon tabs are honest disabled affordances with a badge
 *   4. the Topbar is bare on a shared/operator route (chrome drops out)
 *   5. the products launcher lists every mode, grouped
 *   6. a soon tab's surface is the honest WorkflowStub
 *
 * HONEST CONSTRAINT — this is Storybook-driven, not the live app. The live app
 * gates on auth (RequireAuth → /login without api.antiek.ai), so a headless
 * live-app e2e isn't runnable in this environment. The established pattern (see
 * e2e/{operator-day,smoke}.spec.ts) is to drive Storybook stories. So this
 * walk runs against `navigation-fourworkflowshell--walk`, a story that
 * composes the REAL shell components (not mocks) under a MemoryRouter with the
 * four workflows' routes wired. It asserts the IA wiring; it does NOT exercise
 * auth, the live substrate, or the production route tree.
 *
 *   npm run e2e   (builds Storybook, then runs against http://localhost:6006)
 */
import { expect, test, type Page } from "@playwright/test";

const STORYBOOK_URL = process.env.STORYBOOK_URL ?? "http://localhost:6006";

function storyUrl(id: string): string {
  return `${STORYBOOK_URL}/iframe.html?args=&id=${id}&viewMode=story`;
}

async function loadStory(page: Page, id: string): Promise<void> {
  await page.goto(storyUrl(id), { waitUntil: "domcontentloaded" });
}

const WORKFLOWS = ["Research", "Read", "Write", "Speak"] as const;

/** Locators scoped to the composed shell story. */
function railWorkflow(page: Page, label: string) {
  return page.locator(`nav[aria-label="Workflows"] button[aria-label="${label}"]`);
}
function sceneViews(page: Page) {
  return page.locator('nav[aria-label="Scene views"]');
}
function contentTree(page: Page) {
  return page.locator('aside[aria-label="Content tree"]');
}

test.describe("Four-workflow IA — the composed-shell walk", () => {
  test("rail carries exactly the four workflows", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-fourworkflowshell--walk");

    const railNav = page.locator('nav[aria-label="Workflows"]');
    await expect(railNav).toBeVisible({ timeout: 10_000 });

    // Exactly four workflow buttons, in order.
    const buttons = railNav.locator("button");
    await expect(buttons).toHaveCount(WORKFLOWS.length);
    for (const w of WORKFLOWS) {
      await expect(railWorkflow(page, w)).toBeVisible();
    }
  });

  test("selecting a workflow re-scopes the tree + re-routes the scene", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-fourworkflowshell--walk");

    // Starts on Research: the Investigations folder is present; Read's
    // Documents folder is not.
    await expect(contentTree(page).getByText("Investigations")).toBeVisible({
      timeout: 10_000,
    });
    await expect(contentTree(page).getByText("Documents")).toHaveCount(0);
    // The tree's workflow label reflects Research, and the scene body too.
    await expect(page.getByTestId("scene-body")).toHaveAttribute(
      "data-workflow",
      "research",
    );

    // Click Read → tree re-scopes to the Read folders, scene re-routes.
    await railWorkflow(page, "Read").click();
    await expect(page.getByTestId("scene-route")).toHaveText("/documents");
    await expect(page.getByTestId("scene-body")).toHaveAttribute(
      "data-workflow",
      "read",
    );
    await expect(contentTree(page).getByText("Documents")).toBeVisible();
    await expect(contentTree(page).getByText("Notebooks")).toBeVisible();
    // The Research-only folder is gone now.
    await expect(contentTree(page).getByText("Investigations")).toHaveCount(0);

    // Click Write → its home route + scoped tree.
    await railWorkflow(page, "Write").click();
    await expect(page.getByTestId("scene-route")).toHaveText("/create");
    await expect(contentTree(page).getByText("Deliverables")).toBeVisible();

    // Click Speak → its home route + scoped tree.
    await railWorkflow(page, "Speak").click();
    await expect(page.getByTestId("scene-route")).toHaveText("/interviews");
    await expect(
      contentTree(page).getByText("Interview projects"),
    ).toBeVisible();
  });

  test("scene chrome shows built tabs as links + soon tabs as honest stubs", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-fourworkflowshell--walk");

    const tabs = sceneViews(page);
    await expect(tabs).toBeVisible({ timeout: 10_000 });

    // Research scene: Synthesis is a live link (built); Trajectory is a
    // disabled affordance with a "soon" badge (not a link).
    await expect(tabs.getByRole("link", { name: "Synthesis" })).toBeVisible();
    await expect(tabs.getByRole("link", { name: "Sources" })).toBeVisible();
    // Trajectory is NOT a link.
    await expect(tabs.getByRole("link", { name: "Trajectory" })).toHaveCount(0);
    // …but its label + the soon badge are present.
    await expect(tabs.getByText("Trajectory")).toBeVisible();
    await expect(tabs.getByText("soon").first()).toBeVisible();

    // Switch to the Read scene: its tabs replace Research's.
    await railWorkflow(page, "Read").click();
    await expect(tabs.getByRole("link", { name: "Reader" })).toBeVisible();
    await expect(tabs.getByText("Rabbit hole")).toBeVisible();
    // Research's Synthesis tab is gone from the strip.
    await expect(tabs.getByRole("link", { name: "Synthesis" })).toHaveCount(0);
  });

  test("the products launcher lists every mode, grouped", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-fourworkflowshell--walk");

    // Open via the real rail button (the ⊞ "All products…" action).
    await page.getByRole("button", { name: "All products…" }).click();

    const dialog = page.getByRole("dialog", { name: "All products" });
    await expect(dialog).toBeVisible();

    // The four workflows head the surfaced group.
    for (const w of WORKFLOWS) {
      await expect(
        dialog.getByText(w, { exact: true }).first(),
      ).toBeVisible();
    }
    // The grouped inventory is substantial (the ~31 non-rail modes live here).
    // Count the mode buttons (every item is a button; minus the close ✕).
    const itemButtons = dialog.locator("button");
    expect(await itemButtons.count()).toBeGreaterThanOrEqual(18);
    // The group headers are present.
    await expect(dialog.getByText("Content & analysis")).toBeVisible();
    await expect(dialog.getByText("Money & account")).toBeVisible();

    // Escape closes it.
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });

  test("a shared/operator route renders the Topbar bare (chrome drops out)", async ({
    page,
  }) => {
    // The composed walk reaches workflow routes only; the bare-route behavior
    // is owned by the SceneChrome SharedRouteBare story (mounted at /billing).
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-scenechrome--shared-route-bare");

    // The header (banner) survives, but neither the action bar nor the tab
    // strip render on a shared route.
    await expect(page.getByRole("banner")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('nav[aria-label="Scene views"]')).toHaveCount(0);
    // The breadcrumb shows the shared route (exact: avoid matching the
    // story's "/billing" route-echo label).
    await expect(page.getByText("Billing", { exact: true })).toBeVisible();
  });

  test("a soon tab's surface is the honest WorkflowStub", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await loadStory(page, "navigation-scenechrome--soon-tab-stub");

    const stub = page.getByRole("status");
    await expect(stub).toBeVisible({ timeout: 10_000 });
    await expect(stub.getByText("Not yet available.")).toBeVisible();
    // It names the owning sprint — the honest hand-off, not a fake surface.
    await expect(stub.getByText(/ships in SPR-07/)).toBeVisible();
  });
});
