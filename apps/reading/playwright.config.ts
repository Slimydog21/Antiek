import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the e2e smoke suite.
 *
 *   npm run e2e        # runs against http://localhost:6006 (Storybook)
 *   STORYBOOK_URL=…    # override
 *
 * The webServer block auto-starts `npm run build-storybook && npx
 * http-server storybook-static -p 6006` if no server is on the port.
 * That keeps `npm run e2e` a one-shot operator command.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: process.env.CI
    ? [["github"], ["list"]]
    : [["list"]],
  use: {
    baseURL: process.env.STORYBOOK_URL ?? "http://localhost:6006",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.STORYBOOK_URL
    ? undefined
    : {
        command:
          "npx --yes http-server storybook-static -p 6006 -s --cors",
        url: "http://localhost:6006",
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
