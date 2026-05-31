import { defineConfig } from "vitest/config";

/**
 * vitest config for the AMS-v2 (SPR-01) PURE e2e helpers — the pixel/contrast
 * calibration in e2e/_ams/visible.pixel.test.ts.
 *
 * Separate from the app's jsdom vitest (whose include is `src/**`): these pure
 * helpers decode PNG buffers and compute variance/contrast, so they run in a
 * plain `node` environment with no React/jsdom. The Playwright SPECS in e2e/
 * (smoke, ams-shell, …) are run by Playwright, not vitest — this config only
 * picks up the `*.pixel.test.ts` unit calibration.
 *
 *   npm run test:ams     # from apps/reading
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
    root: __dirname,
    include: ["e2e/_ams/**/*.pixel.test.ts"],
    exclude: ["**/node_modules/**", "**/dist/**"],
  },
});
