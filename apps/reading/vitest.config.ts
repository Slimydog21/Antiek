import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const posthogVitestMock = new URL("./src/test/posthog-js-vitest.ts", import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "posthog-js": posthogVitestMock,
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
