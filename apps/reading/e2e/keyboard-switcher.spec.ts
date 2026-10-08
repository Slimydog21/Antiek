/**
 * keyboard-switcher.spec.ts — journey J3b (FFX-KPA SPR-04 M6).
 *
 * The geared switch on the REAL built app (vite preview, the ams-real
 * project), driven from the keyboard: no mouse click anywhere. The API is
 * mocked at the network layer (installAuthMock + page.route) and the flag
 * is turned on with an init script, exactly as an operator would in
 * devtools. Nothing here touches a real backend.
 *
 * WHICH ROOT THE JOURNEY USES (handoff F3, rigor #2): membersByProject is
 * never fed in production, so a registry project's gear 2 is empty and the
 * only forest with sub-projects is the Default project's investigation
 * forest. The persisted selection therefore starts on the registry project
 * "p1" (root 2) and the journey hops to the DEFAULT root (root 1), goes
 * through the picker, and descends the Default forest. "Project 2" in the
 * sprint page is the Default root here; stated, not hidden.
 *
 * The agent leg: the companion holds no tabs at boot, so the journey first
 * opens the one-shot dialogue agent from the companion's "New agent" menu
 * (focus + Enter, as J3a reached the Stop button), then the switch's gear 3
 * lists it after the "Across projects" divider.
 *
 *   npm run build && STORYBOOK_URL=http://localhost:6006 npx playwright test e2e/keyboard-switcher.spec.ts --project=ams-real
 */
import { expect, test, type Page, type Route } from "@playwright/test";

import { FAKE_IDENTITY, installAuthMock } from "./_ams/auth";

test.use({ video: "on" });

async function json(route: Route, status: number, body: unknown) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const project = (id: string, title: string, order: number) => ({
  project_id: id, title, kind: "project", order, pinned: false, archived_at: null,
  primary_document_id: null, created_at: "2026-09-01T00:00:00Z", updated_at: null, member_count: 0,
});
const inv = (id: string, question: string, started: string, parent: string | null = null) => ({
  investigation_id: id, question, status: "completed", started_at: started, completed_at: started,
  cost_usd_total: 0.1, parent_investigation_id: parent,
});

/** Three forest roots under Default (newest first: inv-c, inv-b, inv-a); inv-b has a child. */
const INVESTIGATIONS = [
  inv("inv-a", "Why does the moon keep one face to us?", "2026-09-10T10:00:00Z"),
  inv("inv-b", "What sets a tidal locking timescale?", "2026-09-11T10:00:00Z"),
  inv("inv-b-child", "Does eccentricity matter?", "2026-09-12T10:00:00Z", "inv-b"),
  inv("inv-c", "Could the moon ever unlock?", "2026-09-13T10:00:00Z"),
];
const PROJECTS = [project("p1", "Varda diligence", 1), project("p2", "Second project", 2)];

async function boot(page: Page): Promise<void> {
  await page.addInitScript((subject: string) => {
    window.localStorage.setItem("antiek.flag.nav.switcher", "on");
    // The persisted account project (persistence.ts PersistedTabProject,
    // account-scoped by accountStorageKey): start on the registry root.
    window.localStorage.setItem(
      `antiek.workspace.tab-project.owner.${encodeURIComponent(subject)}`,
      JSON.stringify({ schemaVersion: 1, projectId: "p1" }),
    );
  }, FAKE_IDENTITY.user_id);
  await installAuthMock(page);
  await page.route("**/projects", (route) => json(route, 200, { projects: PROJECTS }));
  await page.route("**/investigations?*", (route) => json(route, 200, { count: INVESTIGATIONS.length, investigations: INVESTIGATIONS }));
  await page.route("**/investigations", (route) => json(route, 200, { count: INVESTIGATIONS.length, investigations: INVESTIGATIONS }));
  await page.route(/\/investigations\/inv-[\w-]+$/, (route) =>
    json(route, 200, { ...INVESTIGATIONS.find((i) => route.request().url().endsWith(i.investigation_id)), events: [] }));
  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await expect(page.locator("[data-gear-chip]")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("[data-gear-chip]")).toContainText("Varda diligence", { timeout: 20_000 });
  await page.locator("body").click({ position: { x: 4, y: 4 } }); // focus off any field; the only pointer act, before the journey
}

const dialog = (page: Page) => page.locator("[data-gear-switch]");
const cursor = (page: Page) => page.locator('[data-gear-switch] [role="tab"][tabindex="0"]');

test.describe("J3b — the geared switch from the keyboard", () => {
  test("chord → hop to the Default root → picker → gear 2 → second sub-project → gear 3 → agent; Esc", async ({ page }) => {
    await boot(page);

    // The companion's dialogue agent, opened from the keyboard (focus + Enter).
    const newAgent = page.getByRole("button", { name: "New agent" });
    await newAgent.focus();
    await page.keyboard.press("Enter");
    const dialogue = page.getByRole("menuitem", { name: "One-shot dialogue" });
    await dialogue.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menu", { name: "New agent" })).toHaveCount(0);
    await page.locator("body").click({ position: { x: 4, y: 4 } });

    // Gear 1 opens on the current project (p1, root 2).
    await page.keyboard.press("Control+Alt+Shift+KeyW");
    await expect(dialog(page)).toBeVisible();
    await expect(dialog(page)).toHaveAttribute("data-gear", "1");
    await expect(cursor(page)).toHaveAttribute("id", "gear-tab-project-p1");
    await expect(cursor(page)).toBeFocused();

    // Hop to the Default root (the root with a forest, F3) and Enter: the
    // picker opens over the switch with that row focused; Enter picks it.
    await page.keyboard.press("ArrowLeft");
    await expect(cursor(page)).toHaveAttribute("id", "gear-tab-project-default");
    await page.keyboard.press("Enter");
    const picker = page.locator('[data-keymap-owner="project.select"]');
    await expect(picker).toBeVisible();
    await expect(dialog(page)).toBeVisible();
    await expect(picker.locator("button[data-project-row='default']")).toBeFocused({ timeout: 10_000 });
    await page.keyboard.press("Enter");
    await expect(picker).toHaveCount(0);

    // The project arrived: gear 2 is the Default forest (newest first).
    await expect(dialog(page)).toHaveAttribute("data-gear", "2");
    await expect(dialog(page).locator('[role="tablist"]')).toHaveAttribute("aria-level", "2");
    await expect(dialog(page).locator('[role="tablist"]')).toHaveAttribute("aria-label", "Investigations");
    await expect(dialog(page).locator('[role="tab"]')).toHaveText([
      "Could the moon ever unlock?", "What sets a tidal locking timescale?", "Why does the moon keep one face to us?",
    ]);
    await expect(cursor(page)).toBeFocused();

    // Hop to the second sub-project and Enter: the research mothership
    // shows its root tab; the switch stays open at gear 3.
    await page.keyboard.press("ArrowRight");
    await expect(cursor(page)).toHaveAttribute("id", "gear-tab-subproject-inv-b");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/inv\/inv-b(\?|$)/, { timeout: 10_000 });
    await expect(dialog(page)).toHaveAttribute("data-gear", "3");
    await expect(dialog(page).locator('[role="tablist"]')).toHaveAttribute("aria-level", "3");
    await expect(cursor(page)).toBeFocused();
    // The research mothership's strip (DocumentTabStrip's "Top-level tabs"
    // tablist) shows the spawned root as its active tab.
    await expect(page.locator('[role="tablist"][aria-label="Top-level tabs"] [role="tab"][aria-selected="true"]'))
      .toContainText("What sets a tidal locking timescale?");
    // Gear 3: the child investigation first (a drill target), then the
    // cross-project dialogue agent after the divider.
    await expect(dialog(page).locator('[role="tab"]')).toHaveText(["Does eccentricity matter?", "dialogue"]);
    await expect(dialog(page)).toContainText("Across projects");

    // Hop to the agent and Enter: the switch closes, the companion focuses it.
    await page.keyboard.press("End");
    await expect(cursor(page)).toHaveAttribute("id", "gear-tab-agent-agent:dialogue");
    await page.keyboard.press("Enter");
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.locator('[data-pane="right"] [role="tab"][aria-selected="true"]')).toContainText("dialogue");
    const focusedPane = await page.evaluate(() => document.activeElement?.closest("[data-pane]")?.getAttribute("data-pane") ?? null);
    expect(focusedPane).toBe("right");

    // The chip reads the whole path; the strip still shows the mothership tab.
    await expect(page.locator("[data-gear-chip]")).toContainText("Default project");
    await expect(page.locator("[data-gear-chip]")).toContainText("What sets a tidal locking timescale?");
    await expect(page.locator("[data-gear-chip]")).toContainText("dialogue");

    // Esc: reopen and close without selecting; focus returns where it was
    // (the right pane the gear-3 Enter focused), not merely "somewhere".
    const openerPane = () => page.evaluate(() => document.activeElement?.closest("[data-pane]")?.getAttribute("data-pane") ?? null);
    expect(await openerPane()).toBe("right");
    await page.keyboard.press("Control+Alt+Shift+KeyW");
    await expect(dialog(page)).toBeVisible();
    await expect(dialog(page)).toHaveAttribute("data-gear", "1");
    await expect(cursor(page)).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
    await expect(page).toHaveURL(/\/inv\/inv-b(\?|$)/);
    expect(await openerPane()).toBe("right");
  });

  test("modal scope in the real browser: typed characters never reach a text field beneath, Esc returns focus to it; ctrl+alt+l does not move the pane focus and prefix keys do nothing", async ({ page }) => {
    await boot(page);
    // A text field beneath, focused (a notebook block, a composer): the
    // chord has scope "anywhere" and opens the switch from inside it. Real
    // key events through Chromium, which jsdom cannot give (GearSwitch.test
    // can only show the field's listener never fires).
    await page.evaluate(() => {
      const field = document.createElement("textarea");
      field.id = "e2e-beneath";
      field.setAttribute("aria-label", "beneath");
      document.body.append(field);
      field.focus();
    });
    const beneath = page.locator("#e2e-beneath");
    await expect(beneath).toBeFocused();
    await page.keyboard.press("Control+Alt+Shift+KeyW");
    await expect(dialog(page)).toBeVisible();
    await expect(cursor(page)).toBeFocused();
    await page.keyboard.type("abc hl");
    await expect(dialog(page)).toBeVisible();
    await expect(beneath).toHaveValue("");
    expect(await page.evaluate(() => document.activeElement?.closest("[data-gear-switch]") !== null)).toBe(true);
    // A programmatic focus() from beneath (what an editor's chain().focus()
    // does) is pulled back into the switch.
    await page.evaluate(() => document.getElementById("e2e-beneath")?.focus());
    await expect(cursor(page)).toBeFocused();
    await page.keyboard.type("xy");
    await expect(beneath).toHaveValue("");
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
    await expect(beneath).toBeFocused();
    await page.keyboard.type("ok");
    await expect(beneath).toHaveValue("ok");
    await page.evaluate(() => document.getElementById("e2e-beneath")?.remove());
    await page.locator("body").click({ position: { x: 4, y: 4 } });

    await page.keyboard.press("Control+Alt+Shift+KeyW");
    await expect(dialog(page)).toBeVisible();
    const before = await page.evaluate(() => document.activeElement?.id ?? null);
    await page.keyboard.press("Control+Alt+KeyL");
    // The prefix never arms inside the modal: ctrl+b then c would otherwise
    // open the new-tab picker (tab.new); "c" is not a switcher key either.
    await page.keyboard.press("Control+KeyB");
    await page.keyboard.press("KeyC");
    await expect(dialog(page)).toBeVisible();
    await expect(page.locator('[data-keymap-owner="tab.new"]')).toHaveCount(0);
    expect(await page.evaluate(() => document.activeElement?.id ?? null)).toBe(before);
    expect(await page.evaluate(() => document.activeElement?.closest("[data-pane]")?.getAttribute("data-pane") ?? null)).toBeNull();
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
  });
});
