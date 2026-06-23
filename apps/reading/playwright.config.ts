import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e suites.
 *
 *   npm run e2e        # Storybook + AMS real-app gate
 *   npm run e2e:login  # ANT-AUTH-DIAG login surface (LOGIN_E2E vite preview)
 */

const STORYBOOK_BASE = process.env.STORYBOOK_URL ?? "http://localhost:6006";
const AMS_APP_BASE = process.env.AMS_APP_URL ?? "http://localhost:4173";
const LOGIN_APP_BASE = process.env.LOGIN_APP_URL ?? "http://localhost:4173";
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