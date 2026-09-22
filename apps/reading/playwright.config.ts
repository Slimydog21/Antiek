import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e suites.
 *
 *   npm run e2e        # Storybook + AMS real-app gate
 *   npm run e2e:login  # ANT-AUTH-DIAG login surface (LOGIN_E2E vite preview)
 *   npm run e2e:passkey # Real FastAPI + virtual WebAuthn authenticator
 *   npm run test:e2e   # Real FastAPI + real DuckDB, account-memory panel
 */

const STORYBOOK_BASE = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const AMS_APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
const LOGIN_APP_BASE = process.env.LOGIN_APP_URL ?? "http://localhost:4173";
const PASSKEY_APP_BASE = "http://localhost:5173";
const PASSKEY_E2E = process.env.PASSKEY_E2E === "1";
const AMS_BOOTS_PREVIEW = !process.env.AMS_APP_URL;

/**
 * MEMORY_E2E — the account-memory panel against a REAL backend.
 *
 * Ports are deliberately NOT 8000/5173. Those are the operator's own dev
 * backend and dev frontend, and two uvicorns on one graph file is the exact
 * writer-lock conflict `runtime/db_lock.py` exists to prevent. This harness
 * boots its own uvicorn (still `--workers 1`) against its own throwaway DuckDB
 * file under /tmp, so it never opens a second writer on the live graph and
 * never touches the operator's `~/.antiek/` state. Everything it writes lives
 * under MEMORY_STATE_DIR and is deleted on each boot.
 *
 * `localhost` rather than `127.0.0.1` in the URLs is load-bearing: cookies are
 * scoped by host and ignore port, so the session the API sets on
 * localhost:8011 is the one the app on localhost:5183 sends back. The browser
 * resolver rule maps localhost to the loopback the servers actually bind.
 */
const MEMORY_E2E = process.env.MEMORY_E2E === "1";
const MEMORY_API_PORT = 8011;
const MEMORY_APP_PORT = 5183;
const MEMORY_API_BASE = `http://localhost:${MEMORY_API_PORT}`;
const MEMORY_APP_BASE = `http://localhost:${MEMORY_APP_PORT}`;
const MEMORY_STATE_DIR = "/tmp/antiek-memory-playwright";
const MEMORY_DB = `${MEMORY_STATE_DIR}/graph.duckdb`;
/** Repo-root-relative by default; overridable when the checkout is a worktree
 *  that carries no venv of its own. */
const MEMORY_PYTHON = process.env.ANTIEK_PYTHON ?? ".venv/bin/python";

const MEMORY_BACKEND_ENV: Record<string, string> = {
  ANTIEK_AUTH_SECRET: "playwright-memory-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  ANTIEK_OPERATOR_EMAIL: "operator@example.com",
  ANTIEK_COOKIE_INSECURE: "1",
  ANTIEK_DEV_LOGIN_TOKEN: "playwright-memory-bootstrap",
  ANTIEK_DUCKDB_PATH: MEMORY_DB,
  ANTIEK_STATE_DIR: MEMORY_STATE_DIR,
  ANTIEK_RESEARCH_EVENTS_DIR: `${MEMORY_STATE_DIR}/events`,
  ANTIEK_EVENT_LOG_DIR: `${MEMORY_STATE_DIR}/events`,
  ANTIEK_API_BASE_URL: MEMORY_API_BASE,
  ANTIEK_FRONTEND_BASE_URL: MEMORY_APP_BASE,
};

export default defineConfig({
  testDir: "./e2e",
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
      name: "chromium",
      testIgnore:
        /(ams-shell|glass-surface|glass-reduced-motion|windows-default|hotkeys-command-scheme|navrail-labels|token-retone|ams-v2-experience-matrix|ams-v2-resilience-matrix|feel-rw-ide-exempt|feel-experience-matrix|research-hard-ceiling|login-magic-link|passkey-roundtrip|account-memory-panel)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "ams-real",
      testMatch:
        /(ams-shell|glass-surface|glass-reduced-motion|windows-default|hotkeys-command-scheme|navrail-labels|token-retone|ams-v2-experience-matrix|ams-v2-resilience-matrix|feel-rw-ide-exempt|feel-experience-matrix|research-hard-ceiling)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: AMS_APP_BASE },
    },
    {
      name: "login-real",
      testMatch: /login-magic-link\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: LOGIN_APP_BASE },
    },
    {
      name: "passkey-real",
      testMatch: /passkey-roundtrip\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: PASSKEY_APP_BASE,
        launchOptions: { args: ["--host-resolver-rules=MAP localhost 127.0.0.1"] },
      },
    },
    {
      name: "memory-real",
      testMatch: /account-memory-panel\.spec\.ts/,
      // Serialized: the spec seeds and corrects rows for ONE owner against ONE
      // DuckDB writer, so parallel workers would race each other's facts.
      fullyParallel: false,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: MEMORY_APP_BASE,
        launchOptions: { args: ["--host-resolver-rules=MAP localhost 127.0.0.1"] },
      },
    },
  ],
  webServer: [
    ...(process.env.STORYBOOK_URL || PASSKEY_E2E || MEMORY_E2E
      ? []
      : [
          {
            command: "npx --yes http-server storybook-static -p 6006 -s --cors",
            url: "http://localhost:6006",
            reuseExistingServer: true,
            timeout: 30_000,
          },
        ]),
    ...(MEMORY_E2E
      ? [
          {
            // A THROWAWAY graph, minted fresh on every boot. `ensure_initialized`
            // is required: an empty DuckDB file has no `nodes`/`edges` tables, and
            // the route answers a flat 503 rather than failing loudly, so a
            // missing schema looks exactly like a broken panel.
            command:
              `rm -rf ${MEMORY_STATE_DIR} && mkdir -p ${MEMORY_STATE_DIR}/events && ` +
              `${MEMORY_PYTHON} -c "from substrate.graph import ensure_initialized; ensure_initialized()" && ` +
              `${MEMORY_PYTHON} -m uvicorn interfaces.research.api.app:app ` +
              `--host 127.0.0.1 --port ${MEMORY_API_PORT} --workers 1`,
            cwd: "../..",
            env: MEMORY_BACKEND_ENV,
            url: `${MEMORY_API_BASE}/health`,
            reuseExistingServer: false,
            timeout: 180_000,
          },
          {
            command: `npm run dev -- --host 127.0.0.1 --port ${MEMORY_APP_PORT} --strictPort`,
            env: { ANTIEK_DEV_API_TARGET: `http://127.0.0.1:${MEMORY_API_PORT}` },
            url: MEMORY_APP_BASE,
            reuseExistingServer: false,
            timeout: 90_000,
          },
        ]
      : PASSKEY_E2E
      ? [
          {
            command:
              "rm -f /tmp/antiek-passkey-playwright.json && cd ../.. && " +
              "ANTIEK_AUTH_SECRET=playwright-passkey-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx " +
              "ANTIEK_OPERATOR_EMAIL=operator@example.com ANTIEK_COOKIE_INSECURE=1 " +
              "ANTIEK_WEBAUTHN_RP_ID=localhost ANTIEK_WEBAUTHN_ORIGINS=http://localhost:5173 " +
              "ANTIEK_PASSKEY_STORE=/tmp/antiek-passkey-playwright.json " +
              "ANTIEK_DEV_LOGIN_TOKEN=playwright-passkey-bootstrap " +
              "ANTIEK_API_BASE_URL=http://localhost:8000 ANTIEK_FRONTEND_BASE_URL=http://localhost:5173 " +
              ".venv/bin/uvicorn interfaces.research.api.app:app --host 127.0.0.1 --port 8000 --workers 1",
            url: "http://localhost:8000/health",
            reuseExistingServer: false,
            timeout: 120_000,
          },
          {
            command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
            url: PASSKEY_APP_BASE,
            reuseExistingServer: false,
            timeout: 60_000,
          },
        ]
      : process.env.LOGIN_E2E
      ? [
          {
            command: "npm run build && npx vite preview --port 4173 --strictPort",
            url: LOGIN_APP_BASE,
            reuseExistingServer: !process.env.CI,
            timeout: 240_000,
          },
        ]
      : AMS_BOOTS_PREVIEW
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
