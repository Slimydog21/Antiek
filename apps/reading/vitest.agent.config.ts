import { defineConfig } from "vitest/config";

/**
 * vitest config for repo-root `tools/agent/` handoff linter (ANT-EXEC-H2V SPR-03).
 *
 *   npm run test:handoff     # from apps/reading
 */
export default defineConfig({
  test: {
    environment: "node",
    globals: false,
    root: __dirname,
    include: ["../../tools/agent/**/*.test.ts"],
    exclude: ["**/node_modules/**"],
  },
});