import { defineConfig } from "vitest/config";

/**
 * vitest config for the repo-root `tools/specs` ref-lint (SPR-01, AMS-v2).
 *
 * The ref-lint lives at `<repo>/tools/specs/` (outside apps/reading's `src`),
 * is a plain Node script (it shells out to `git cat-file` + reads the FS), and
 * must NOT run under the app's jsdom/react config. This config lives inside
 * apps/reading only because that is where node_modules (vitest) resolves; it
 * reaches up to the repo-root tool via a relative include.
 *
 *   npm run test:reflint     # from apps/reading
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
    root: __dirname,
    include: ["../../tools/specs/**/*.test.ts"],
    exclude: ["**/node_modules/**"],
  },
});
