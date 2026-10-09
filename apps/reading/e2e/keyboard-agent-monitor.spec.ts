/**
 * keyboard-agent-monitor.spec.ts — SPR-10 J5: monitoring the agents that
 * work for you, keyboard only, in a real Chromium against the REAL app.
 *
 *   1. two research agents opened as companion tabs through the goto picker
 *      (ctrl+alt+g, / search, Enter); the first refocused so the second is
 *      in the background;
 *   2. the scripted list flips the background agent to completed → the
 *      "finished" toast → prefix+shift+j lands on it → its dot reads idle
 *      (done persisted until that focus);
 *   3. the blocked leg through the DEV seam `window.__antiekAgentStatus
 *      .setNeedsInput` (no wire carries needs-input; handoff §6.1, weaker
 *      than a wire) → "needs you" → prefix+shift+j → the agent is active;
 *      cleared, then completed while ACTIVE → stays done (no toast, not
 *      seen) until the picker focuses it again → idle;
 *   4. axe on the companion strip; zero clicks (a document-level counter).
 *
 * Needs a DEV app (the seam is DEV-only): AMS_APP_URL=<vite dev server
 * with ANTIEK_DEV_API_TARGET pointing at a dead port>. The list is scripted
 * at the network layer (`page.route`); nothing reaches a backend. The
 * routes are PATH-ANCHORED regexes, not _ams/auth.ts's installAuthMock:
 * its `**\/krea/**` glob is harmless against a bundled preview but on a dev
 * server it also catches the source modules under src/**\/krea/** and feeds
 * them JSON ("Failed to load module script ... MIME type application/json"),
 * so the app never boots. Recording and screenshots land under
 * specs/.../ground/j5/.
 */
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

import { FAKE_IDENTITY } from "./_ams/auth";

/** Where the recording and screenshots land: the spec directory's ground/j5
 *  when J5_GROUND_DIR names it (the harness run), else test-results/j5. */
const GROUND = process.env.J5_GROUND_DIR
  ? resolve(process.env.J5_GROUND_DIR)
  : resolve(dirname(fileURLToPath(import.meta.url)), "../test-results/j5");
let videoPath: string | null = null;

test.use({ video: { mode: "on", size: { width: 1280, height: 800 } }, viewport: { width: 1280, height: 800 } });
// A dev server transforms the app on first load; the journey itself waits on
// two 2 s polls and the 3 s startup grace.
test.setTimeout(120_000);

interface Row {
  investigation_id: string;
  question: string;
  status: "in_progress" | "completed";
  started_at: string;
  completed_at: string | null;
  cost_usd_total: number;
  parent_investigation_id: null;
}

const row = (id: string, question: string, status: Row["status"], completed_at: string | null = null): Row => ({
  investigation_id: id,
  question,
  status,
  started_at: "2026-10-07T20:00:00Z",
  completed_at,
  cost_usd_total: 0.1,
  parent_investigation_id: null,
});

const json = (r: Route, status: number, body: unknown) =>
  r.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/** An API path on the app origin (never a `/src/...` module). */
const api = (path: string) => new RegExp(`^https?://[^/]+${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\?.*)?$`);

async function installRoutes(page: Page, rows: Map<string, Row>): Promise<void> {
  await page.route(api("/auth/me"), (r) => json(r, 200, FAKE_IDENTITY));
  await page.route(api("/auth/logout"), (r) => r.fulfill({ status: 204, body: "" }));
  await page.route(api("/krea/scene"), (r) => json(r, 200, { art: null, mood: null }));
  await page.route(api("/krea/status"), (r) => json(r, 200, {
    enabled: false, key_present: false, kill_switch: false, gate_verdict: "no_key", reasons: ["no_key"],
    budget: { spent_today: 0, cap: 0, remaining: 0 }, rate_window: { occupancy: 0, max: 0, window_s: 60 },
    cache: { entries: 0, max_entries: 0 }, last_success_at: null, failure_counts: {}, failures: [],
  }));
  await page.route(api("/investigations"), (r) => json(r, 200, { count: rows.size, investigations: [...rows.values()] }));
  await page.route(/^https?:\/\/[^/]+\/investigations\/[^/?]+/, (r) => json(r, 404, { detail: "scripted: the per-id route is never read by SPR-10" }));
  await page.route(api("/projects"), (r) => json(r, 200, { projects: [] }));
}

const dot = (page: Page, id: string) => page.locator(`[data-agent-tab="agent:thread:${id}"] [role="tab"] [role="img"]`);
const activeTab = (page: Page) => page.locator('[data-agent-strip-row] [role="tab"][aria-selected="true"]');
const toasts = (page: Page) => page.locator('[role="status"]:not(.antiek-prefix-chip__region)');

/** Keyboard only: ctrl+alt+g, "/" to the search, the title, Enter. */
async function viaPicker(page: Page, title: string): Promise<void> {
  await page.keyboard.press("Control+Alt+g");
  const picker = page.locator('[data-keymap-owner="agents.goto"]');
  await expect(picker).toBeVisible({ timeout: 5_000 });
  await expect(picker.locator('[role="option"]').first()).toBeVisible({ timeout: 5_000 });
  await page.keyboard.press("/");
  await expect(picker.getByRole("searchbox", { name: "Search agents" })).toBeFocused();
  await page.keyboard.type(title);
  await expect(picker.locator('[role="option"] [data-row-title]')).toHaveText([title]);
  await page.keyboard.press("Enter");
  await expect(picker).toBeHidden({ timeout: 5_000 });
  await expect(activeTab(page)).toContainText(title, { timeout: 5_000 });
}

/** The Research home autofocuses its question box and the picker hands
 *  focus back to it on close. The prefix never arms from a text field (by
 *  design, keymap.ts), so Tab out first; still keyboard only. */
async function leaveText(page: Page): Promise<void> {
  for (let i = 0; i < 6; i++) {
    const inText = await page.evaluate(() => {
      const el = document.activeElement;
      return !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || (el as HTMLElement).isContentEditable);
    });
    if (!inText) return;
    await page.keyboard.press("Tab");
  }
  throw new Error("could not leave the text field by Tab");
}

async function toastJump(page: Page): Promise<void> {
  await leaveText(page);
  await page.keyboard.press("Control+b");
  await page.keyboard.press("Shift+J");
}

test.afterAll(() => {
  if (videoPath && existsSync(videoPath)) {
    mkdirSync(GROUND, { recursive: true });
    copyFileSync(videoPath, join(GROUND, "j5-keyboard-agent-monitor.webm"));
  }
});

test("J5 — finished and needs-you toasts, one key lands on the agent, done persists until focused", async ({ page }) => {
  mkdirSync(GROUND, { recursive: true });
  const rows = new Map<string, Row>([
    ["inv-a", row("inv-a", "Alpha agent", "in_progress")],
    ["inv-b", row("inv-b", "Beta agent", "in_progress")],
  ]);
  await installRoutes(page, rows);
  await page.addInitScript(() => {
    (window as unknown as { __clicks: number }).__clicks = 0;
    for (const ev of ["click", "mousedown", "pointerdown"]) {
      document.addEventListener(ev, () => { (window as unknown as { __clicks: number }).__clicks += 1; }, true);
    }
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => (document.getElementById("root")?.childElementCount ?? 0) > 0, undefined, { timeout: 30_000 });
  await expect(page.locator("[data-agent-strip-row]")).toBeVisible({ timeout: 30_000 });
  videoPath = (await page.video()?.path()) ?? null;

  // 1. Two agents as tabs, keyboard only; A refocused so B is background.
  await viaPicker(page, "Alpha agent");
  // The picker's rows come from the tree the lazy AgentMonitorFeed feeds, so
  // by now the status store has started: its 3 s startup grace (which
  // swallows transitions by design) is measured from here, not from goto.
  const tStoreStarted = Date.now();
  await viaPicker(page, "Beta agent");
  await viaPicker(page, "Alpha agent");
  await expect(dot(page, "inv-a")).toHaveAttribute("data-status", "working");
  await expect(dot(page, "inv-b")).toHaveAttribute("data-status", "working");
  await page.screenshot({ path: join(GROUND, "01-two-agents-working.png") });

  // Past the 3 s startup grace before any transition.
  const elapsed = Date.now() - tStoreStarted;
  if (elapsed < 3_500) await page.waitForTimeout(3_500 - elapsed);

  // 2. B completes in the background → "finished" → done until focused.
  rows.set("inv-b", row("inv-b", "Beta agent", "completed", new Date().toISOString()));
  await expect(toasts(page)).toContainText("Beta agent finished", { timeout: 10_000 });
  await expect(dot(page, "inv-b")).toHaveAttribute("data-status", "done");
  await expect(activeTab(page)).toContainText("Alpha agent");
  await page.screenshot({ path: join(GROUND, "02-finished-toast.png") });
  await toastJump(page);
  await expect(activeTab(page)).toContainText("Beta agent", { timeout: 5_000 });
  await expect(dot(page, "inv-b")).toHaveAttribute("data-status", "idle");
  await expect(toasts(page)).not.toContainText("finished");
  await page.screenshot({ path: join(GROUND, "03-after-key-idle.png") });

  // 3. Blocked leg through the DEV seam (A is background now).
  const seam = await page.evaluate(() => typeof window.__antiekAgentStatus?.setNeedsInput === "function");
  expect(seam, "the DEV seam window.__antiekAgentStatus is required (vite dev server)").toBe(true);
  await page.evaluate(() => window.__antiekAgentStatus!.setNeedsInput("inv-a", true));
  await expect(toasts(page)).toContainText("Alpha agent needs you", { timeout: 5_000 });
  await expect(dot(page, "inv-a")).toHaveAttribute("data-status", "blocked");
  await page.screenshot({ path: join(GROUND, "04-needs-you-toast.png") });
  await toastJump(page);
  await expect(activeTab(page)).toContainText("Alpha agent", { timeout: 5_000 });
  await expect(toasts(page)).not.toContainText("needs you");
  await page.evaluate(() => window.__antiekAgentStatus!.setNeedsInput("inv-a", false));
  await expect(dot(page, "inv-a")).toHaveAttribute("data-status", "working");
  // Completed while ACTIVE: no toast, and done persists until a focus.
  rows.set("inv-a", row("inv-a", "Alpha agent", "completed", new Date().toISOString()));
  await expect(dot(page, "inv-a")).toHaveAttribute("data-status", "done", { timeout: 10_000 });
  await page.waitForTimeout(500);
  await expect(toasts(page)).not.toContainText("Alpha agent finished");
  await viaPicker(page, "Alpha agent");
  await expect(dot(page, "inv-a")).toHaveAttribute("data-status", "idle");
  await page.screenshot({ path: join(GROUND, "05-done-until-focused-then-idle.png") });

  // 4. The strip is accessible; nothing was clicked.
  const axe = await new AxeBuilder({ page }).include("[data-agent-strip-row]").analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  expect(await page.evaluate(() => (window as unknown as { __clicks: number }).__clicks)).toBe(0);
});
