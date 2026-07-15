/**
 * _ams/auth.ts — the real-app login + boot helper (SPR-01, milestone 3).
 *
 * THE GAP THIS FILLS (rigor #1 — record the gap, don't paper it)
 * --------------------------------------------------------------
 * The SPR-01 brief said "reuse the auth/login helper from e2e/smoke.spec.ts."
 * Verification (`git show origin/main:apps/reading/e2e/smoke.spec.ts`) shows
 * that file has NO auth helper — it loads Storybook iframes via `storyUrl()`.
 * There is no real-app authed e2e path on origin/main today. So this helper is
 * NEW-to-build, recorded as such in docs/ams-v2/verified-interfaces.md §8/§10.
 *
 * HOW IT GETS PAST RequireAuth WITHOUT TOUCHING APP CODE
 * ------------------------------------------------------
 * The real auth contract (verified in src/lib/auth.tsx) is:
 *
 *   AuthProvider → on mount calls GET `${API_BASE}/auth/me`
 *     200 { user_id, email, auth_method }  ⇒ state = "authenticated"
 *     401 / network error                  ⇒ state = "unauthenticated"
 *   RequireAuth (src/App.tsx) renders children ONLY when authenticated,
 *   else <Navigate to="/login?next=…">.
 *
 * Under `vite preview` with VITE_API_BASE_URL unset, API_BASE === "" so the
 * request is same-origin: `<baseURL>/auth/me`. We therefore intercept the
 * glob "(star-star-slash)auth/me" at the Playwright NETWORK layer and fulfil it
 * with a 200 + a fake authed identity. This is a TEST-SIDE network mock — it adds ZERO
 * auth-bypass to the production bundle (the brief's hard requirement: "NO
 * prod app-code auth bypass"). The shipped app still demands a real session;
 * only this browser context sees the mocked response.
 *
 * We additionally stub the other auth endpoints + a couple of always-on
 * substrate reads that would otherwise 404/hang under preview (there is no
 * FastAPI in the harness), keeping the shell from erroring on boot. None of
 * these touch product correctness — SPR-10 runs the full matrix; SPR-01 only
 * needs the shell to MOUNT so the scene/window/igloo anchors can be asserted.
 */

import type { Page, Route } from "@playwright/test";

/** The fake identity the mocked /auth/me returns. Matches AuthIdentity. */
export const FAKE_IDENTITY = {
  user_id: "ams-e2e-operator",
  email: "operator@ams.e2e",
  auth_method: "ams-e2e-mock",
} as const;

/** Fulfil a Playwright route with JSON. */
async function json(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

/**
 * Install the auth + minimal-substrate network mocks on a page's context.
 * Idempotent-ish: call once per page before navigating.
 *
 * The ONLY load-bearing mock is the auth/me one (200 FAKE_IDENTITY), which is
 * what flips RequireAuth from redirect-to-login into render-children.
 */
export async function installAuthMock(page: Page): Promise<void> {
  // 1) THE load-bearing one: a valid authed session.
  await page.route("**/auth/me", (route) => json(route, 200, FAKE_IDENTITY));

  // 2) Logout / request endpoints — harmless stubs so any stray call resolves.
  await page.route("**/auth/logout", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/auth/request", (route) => json(route, 200, { sent: true }));

  // 3) Krea is operator-token-gated and absent in the harness (RULE 3 — the
  //    scene must be visible WITHOUT the paid stream). Return graceful-absence
  //    so the procedural scene renders and nothing throws.
  await page.route("**/krea/scene", (route) => json(route, 200, { art: null, mood: null }));
  await page.route("**/krea/**", (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/krea/status")) {
      return json(route, 200, {
        enabled: false,
        key_present: false,
        kill_switch: false,
        gate_verdict: "no_key",
        reasons: ["no_key"],
        budget: { spent_today: 0, cap: 0, remaining: 0 },
        rate_window: { occupancy: 0, max: 0, window_s: 60 },
        cache: { entries: 0, max_entries: 0 },
        last_success_at: null,
        failure_counts: {},
        failures: [],
      });
    }
    return json(route, 200, { art: null });
  });
}

/** Options for `loginAndGotoApp`. */
export interface LoginGotoOptions {
  /** Extra wait after navigation for the shell to mount (ms). Default 600. */
  settleMs?: number;
  /** Playwright waitUntil. Default "domcontentloaded" (SPA — no networkidle). */
  waitUntil?: "load" | "domcontentloaded" | "commit";
}

/**
 * Boot the REAL app authenticated and land on `route` (default "/").
 *
 * 1) installs the network auth mock (so RequireAuth passes),
 * 2) navigates to `route` against the page's baseURL (the vite-preview SPA),
 * 3) waits for the app root to mount + a short settle so the canvas scene
 *    paints at least one frame before any pixel assertion runs.
 *
 * Returns nothing; the page is left on the authed route, ready for the
 * _ams/visible.ts assertions. It does NOT assert success itself — the caller
 * decides what "visible" means (that is the whole point of the harness).
 */
export async function loginAndGotoApp(
  page: Page,
  route: string = "/",
  opts: LoginGotoOptions = {},
): Promise<void> {
  const { settleMs = 600, waitUntil = "domcontentloaded" } = opts;
  await installAuthMock(page);
  await page.goto(route, { waitUntil });
  // The app mounts into #root (vite index.html). Wait for it to have children
  // (RequireAuth resolved → AppShell rendered) rather than a fixed sleep alone.
  await page
    .waitForFunction(() => {
      const root = document.getElementById("root");
      return !!root && root.childElementCount > 0;
    }, { timeout: 10_000 })
    .catch(() => {
      /* fall through — the caller's assertion will produce the real diagnosis */
    });
  // Give canvas/rAF layers a beat to paint a frame (scene is rAF-driven).
  await page.waitForTimeout(settleMs);
}
