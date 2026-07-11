import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// ESM-safe dirname (vitest --configLoader runner does not provide __dirname).
const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Worktree may not have every optional browser dep installed; tests only
    // need a resolveable module surface for Settings passkey imports.
    alias: {
      "@simplewebauthn/browser": path.resolve(
        rootDir,
        "src/test-stubs/simplewebauthn-browser.ts",
      ),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.{ts,tsx}"],
    // Storybook stories aren't tests
    exclude: ["**/node_modules/**", "**/dist/**", "**/storybook-static/**"],
  },
});
