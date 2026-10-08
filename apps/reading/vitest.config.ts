import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  // tools/*.test.ts live above this vite root. Collecting them without
  // widening fs.allow yields "Cannot find module '/@fs/.../verify_handoff
  // .test.ts'" for every one -- vitest finds the files, then refuses to serve
  // them. This is a test-runner module-resolution boundary, not a served
  // surface: `vitest run` has no long-lived dev server.
  server: { fs: { allow: [path.resolve(__dirname, "../..")] } },
  test: {
    environment: "jsdom",
    globals: false,
    // Node >= 25 installs a built-in `localStorage` global (web storage,
    // on by default) whose methods are absent without --localstorage-file.
    // jsdom leaves that global in place, so window.localStorage.clear /
    // removeItem / setItem throw "is not a function" at 0 ms in every test
    // that touches storage (reproduced on an untouched file: 11/11 red on
    // Node 25.6.1, 11/11 green with this flag). CI runs Node 20/22 and never
    // saw it; local and compute runs on the Mac mini (/usr/local/bin/node
    // = 25) did. The flag is a no-op on Node 20/22.
    // Node 20 (CI's vitest job) does not know the flag, so it is only passed
    // where it exists (added in Node 22.4).
    execArgv: Number(process.versions.node.split(".")[0]) >= 22
      ? ["--no-experimental-webstorage"]
      : [],
    setupFiles: ["./src/testAccountOwner.ts"],
    // e2e/ holds Playwright specs (*.spec.ts, see playwright.config.ts
    // testMatch) AND pure-function unit calibrations named *.test.ts. The
    // latter matched NEITHER runner: outside this include glob, and excluded
    // by Playwright's /\.spec\.ts$/. e2e/_ams/visible.pixel.test.ts -- the
    // calibration proving assertSceneVisible FAILS on an occluded scene
    // rather than passing vacuously -- had therefore never executed. The two
    // runners stay disjoint by suffix: vitest takes *.test.ts, Playwright
    // takes *.spec.ts, so nothing runs twice.
    // ../../tools/**: verify_handoff.ts (run by scripts/canonical_verify.sh)
    // and verify_spec_refs.ts (scripts/agent_ams_ref_lint.sh) are live tools
    // whose unit tests no runner collected -- there is no root package.json,
    // and this is the repo's only vitest config.
    include: [
      "src/**/*.test.{ts,tsx}",
      "e2e/**/*.test.ts",
      // scripts/bundle_budget.ts picks the file each bundle budget measures;
      // its unit tests are the gate's own negative controls.
      "scripts/**/*.test.ts",
      "../../tools/**/*.test.ts",
      // The dev-server proxy config's own tests (A-19).
      "vite.config.test.ts",
    ],
    // Storybook stories aren't tests
    exclude: ["**/node_modules/**", "**/dist/**", "**/storybook-static/**"],
  },
});
