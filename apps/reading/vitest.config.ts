import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    // e2e/ holds Playwright specs (*.spec.ts, see playwright.config.ts
    // testMatch) AND pure-function unit calibrations named *.test.ts. The
    // latter matched NEITHER runner: outside this include glob, and excluded
    // by Playwright's /\.spec\.ts$/. e2e/_ams/visible.pixel.test.ts -- the
    // calibration proving assertSceneVisible FAILS on an occluded scene
    // rather than passing vacuously -- had therefore never executed. The two
    // runners stay disjoint by suffix: vitest takes *.test.ts, Playwright
    // takes *.spec.ts, so nothing runs twice.
    include: ["src/**/*.test.{ts,tsx}", "e2e/**/*.test.ts"],
    // Storybook stories aren't tests
    exclude: ["**/node_modules/**", "**/dist/**", "**/storybook-static/**"],
  },
});
