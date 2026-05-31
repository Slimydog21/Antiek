import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e suites.
 *
 *   npm run e2e        # Storybook smoke (http://localhost:6006) + AMS real-app gate
 *   STORYBOOK_URL=…    # override the Storybook base
 *   AMS_APP_URL=…      # override the real-app SPA base (else vite preview boots it)
 *
 * TWO PROJECTS (AMS-v2 SPR-01 added the second; the first is UNCHANGED):
 *   - "chromium"  — the existing 8 Storybook specs. baseURL = Storybook (from
 *                   the top-level `use`). It IGNORES ams-shell.spec.ts so the
 *                   real-app spec never runs against the Storybook base.
 *   - "ams-real"  — the NEW real-app experience gate (ams-shell.spec.ts only).
 *                   It loads the REAL authed SPA (not Storybook iframes) and
 *                   pixel/DOM-asserts the visible outcome. Its baseURL is
 *                   AMS_APP_URL, or the vite-preview server below.
 *
 * The original webServer (Storybook static on :6006) is UNCHANGED. A SECOND
 * webServer entry boots `vite preview` for the real-app gate, and only when the
 * operator did NOT point AMS_APP_URL at an external server.
 *
 * RULE 3 (procedural floor): the real-app gate must not hard-depend on a server
 * a CI sandbox can't boot. The ams-shell anchors are `test.fixme` (they don't
 * run) until a later sprint un-fixmes them, so on a sandbox the suite stays
 * green even if the preview server is degraded. SPR-10 runs them for real with
 * a built SPA + AMS_APP_URL. See docs/ams-v2/e2e-harness.md.
 */

const STORYBOOK_BASE = process.env.STORYBOOK_URL ?? "http://localhost:6006";
// The real-app gate's base. If AMS_APP_URL is unset, the vite-preview webServer
// (below) serves the built SPA on :4173 (Vite preview's default port).
const AMS_APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
// Only auto-boot a real-app server when the operator did NOT point at one.
const AMS_BOOTS_PREVIEW = !process.env.AMS_APP_URL;

export default defineConfig({
  testDir: "./e2e",
  // Playwright owns ONLY *.spec.ts. The AMS-v2 PURE-helper unit calibration
  // (e2e/_ams/*.pixel.test.ts) is a VITEST file run by `npm run test:ams`, not
  // a Playwright spec — exclude *.test.ts so Playwright doesn't try to collect
  // it (its `describe`/`it` come from vitest, not @playwright/test).
  testMatch: /\.spec\.ts$/,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: process.env.CI
    ? [["github"], ["list"]]
    : [["list"]],
  use: {
    baseURL: STORYBOOK_BASE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      // UNCHANGED behaviour — the existing 8 Storybook specs. The ONLY addition
      // is `testIgnore` so the new real-app spec doesn't run against Storybook.
      name: "chromium",
      testIgnore: /ams-shell\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      // NEW (SPR-01) — the real-app experience gate. ONLY ams-shell.spec.ts,
      // against the real SPA base (not Storybook).
      name: "ams-real",
      testMatch: /ams-shell\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: AMS_APP_BASE },
    },
  ],
  webServer: [
    // UNCHANGED — Storybook static server on :6006.
    ...(process.env.STORYBOOK_URL
      ? []
      : [
          {
            command: "npx --yes http-server storybook-static -p 6006 -s --cors",
            url: "http://localhost:6006",
            reuseExistingServer: true,
            timeout: 30_000,
          },
        ]),
    // NEW (SPR-01) — the real-app SPA via vite preview, only when AMS_APP_URL
    // is unset. `npm run build` must have produced dist/ first (the e2e script
    // does). reuseExistingServer lets a hand-started preview be reused.
    ...(AMS_BOOTS_PREVIEW
      ? [
          {
            command: "npx vite preview --port 4173 --strictPort",
            url: AMS_APP_BASE,
            reuseExistingServer: true,
            timeout: 60_000,
          },
        ]
      : []),
  ],
});
