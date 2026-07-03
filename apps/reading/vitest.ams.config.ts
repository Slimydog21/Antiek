import { defineConfig } from "vitest/config";

/**
 * vitest config for the AMS-v2 PURE e2e helpers — pixel/contrast calibration
 * plus small Node-only evidence/contract helpers under e2e/_ams.
 *
 * Separate from the app's jsdom vitest (whose include is `src/**`): these pure
 * helpers decode PNG buffers and compute variance/contrast, so they run in a
 * plain `node` environment with no React/jsdom. The Playwright SPECS in e2e/
 * (smoke, ams-shell, …) are run by Playwright, not vitest — this config only
 * picks up `_ams` unit helpers.
 *
 *   npm run test:ams     # from apps/reading
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
    root: __dirname,
    include: ["e2e/_ams/**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/dist/**"],
  },
});
