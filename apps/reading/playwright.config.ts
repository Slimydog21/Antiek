import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e suites.
 *
 *   npm run e2e        # Storybook + AMS real-app gate
 *   npm run e2e:login  # ANT-AUTH-DIAG login surface (LOGIN_E2E vite preview)
 */

const STORYBOOK_BASE = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const AMS_APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
const LOGIN_APP_BASE = process.env.LOGIN_APP_URL ?? "http://127.0.0.1:4173";
const LOGIN_API_BASE = process.env.LOGIN_API_URL ?? "http://127.0.0.1:8000";
const LOGIN_AUTH_SECRET =
  process.env.ANTIEK_AUTH_SECRET
  ?? "antiek-login-e2e-not-a-production-secret-xxxxxxxxxxxxxxxxxxxx";
const LOGIN_OUTBOX =
  process.env.ANTIEK_MOCK_EMAIL_OUTBOX_PATH
  ?? path.join(os.tmpdir(), `antiek-login-e2e-${process.pid}.jsonl`);
const AMS_BOOTS_PREVIEW = !process.env.AMS_APP_URL;

process.env.ANTIEK_AUTH_SECRET = LOGIN_AUTH_SECRET;
process.env.ANTIEK_MOCK_EMAIL_OUTBOX_PATH = LOGIN_OUTBOX;

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
        /(ams-shell|glass-surface|glass-reduced-motion|windows-default|hotkeys-command-scheme|navrail-labels|token-retone|ams-v2-experience-matrix|ams-v2-resilience-matrix|feel-rw-ide-exempt|feel-experience-matrix|login-magic-link)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "ams-real",
      testMatch:
        /(ams-shell|glass-surface|glass-reduced-motion|windows-default|hotkeys-command-scheme|navrail-labels|token-retone|ams-v2-experience-matrix|ams-v2-resilience-matrix|feel-rw-ide-exempt|feel-experience-matrix)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: AMS_APP_BASE },
    },
    {
      name: "login-real",
      testMatch: /login-magic-link\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: LOGIN_APP_BASE },
    },
  ],
  webServer: [
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
    ...(process.env.LOGIN_E2E
      ? [
          {
            command:
              "cd ../.. && "
              + `ANTIEK_AUTH_SECRET=${LOGIN_AUTH_SECRET} `
              + "ANTIEK_OPERATOR_EMAIL=test@antiek.test "
              + "ANTIEK_COOKIE_INSECURE=1 "
              + "ANTIEK_EMAIL_PROVIDER=mock "
              + `ANTIEK_MOCK_EMAIL_OUTBOX_PATH=${LOGIN_OUTBOX} `
              + `ANTIEK_API_BASE_URL=${LOGIN_API_BASE} `
              + `ANTIEK_FRONTEND_BASE_URL=${LOGIN_APP_BASE} `
              + `ANTIEK_CORS_ORIGINS=${LOGIN_APP_BASE},http://localhost:4173 `
              + "uv run --extra dev --extra urls --extra extraction "
              + "uvicorn interfaces.research.api.app:app --host 127.0.0.1 --port 8000",
            url: `${LOGIN_API_BASE}/health`,
            reuseExistingServer: !process.env.CI,
            timeout: 240_000,
          },
          {
            command: `VITE_API_BASE_URL=${LOGIN_API_BASE} npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort`,
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
