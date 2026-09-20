import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e suites.
 *
 *   npm run e2e        # Storybook + AMS real-app gate
 *   npm run e2e:login  # ANT-AUTH-DIAG login surface (LOGIN_E2E vite preview)
 *   npm run e2e:passkey # Real FastAPI + virtual WebAuthn authenticator
 */

const STORYBOOK_BASE = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const AMS_APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
const LOGIN_APP_BASE = process.env.LOGIN_APP_URL ?? "http://localhost:4173";
const PASSKEY_APP_BASE = "http://localhost:5173";
const PASSKEY_E2E = process.env.PASSKEY_E2E === "1";
const AMS_BOOTS_PREVIEW = !process.env.AMS_APP_URL;

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
        /(ams-shell|glass-surface|glass-reduced-motion|windows-default|hotkeys-command-scheme|navrail-labels|token-retone|ams-v2-experience-matrix|ams-v2-resilience-matrix|feel-rw-ide-exempt|feel-experience-matrix|research-hard-ceiling|login-magic-link|passkey-roundtrip)\.spec\.ts/,
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
  ],
  webServer: [
    ...(process.env.STORYBOOK_URL || PASSKEY_E2E
      ? []
      : [
          {
            command: "npx --yes http-server storybook-static -p 6006 -s --cors",
            url: "http://localhost:6006",
            reuseExistingServer: true,
            timeout: 30_000,
          },
        ]),
    ...(PASSKEY_E2E
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
