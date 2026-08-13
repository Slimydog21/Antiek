import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Use the literal loopback address for the proxy target. Newer Node releases
// may resolve `localhost` to IPv6 first while uvicorn listens on IPv4, leaving
// browser fetches hanging even though direct navigation succeeds.
const API_TARGET = "http://127.0.0.1:8000";

// In dev, the Python substrate runs at http://localhost:8000. We could
// either proxy here or rely on CORS on the backend. We do BOTH — proxy
// is the primary path so no cross-origin happens in the browser, CORS
// is the fallback in case the operator runs the frontend somewhere
// other than this Vite dev server.
//
// The backend exposes routes at /health, /events/typed, /trajectory/*,
// and /ws/events. We proxy each prefix individually rather than
// blanket-proxying — keeps the dev path explicit.

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": API_TARGET,
      "/api": API_TARGET,
      "/events": API_TARGET,
      "/trajectory": API_TARGET,
      // The cascade plan/launch/session surface (cascade_routes.py, prefix
      // /research). The Research-entry cascade mode + the DRW monitor both
      // call it; without this proxy a dev drive can't reach the backend.
      "/research": API_TARGET,
      "/styles": API_TARGET,
      "/artifacts": API_TARGET,
      // Metadata-only Library catalog. Keep this explicit rather than using a
      // blanket proxy so body-serving routes remain independently reviewed.
      "/library": API_TARGET,
      // Magic-link auth (H6): both /auth/request/me and the
      // /auth/callback redirect need to be same-origin with the
      // page or the browser drops Set-Cookie.
      "/auth": API_TARGET,
      // Mountain Shell SPR-02 — the Krea scene-art proxy
      // (krea_routes.py). Same-origin in dev so the browser never sees
      // the server-held KREA_API_TOKEN and no CORS is involved.
      "/krea": API_TARGET,
      // Own Your Mind P0 (explain_routes.py + ops_routes.py): the
      // provenance + ops surfaces. Same explicit-prefix discipline as the
      // routes above — each new backend prefix gets a reviewed line here.
      "/claims": API_TARGET,
      "/syntheses": API_TARGET,
      "/docs": API_TARGET,
      "/ops": API_TARGET,
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // S1 acceptance: "Bundle size of lemon/ chunk < 12 KB gzipped".
        // Force the design-system primitives into their own chunk so the
        // budget is measurable. The lemon chunk is shared between the
        // main app + Storybook stories + RTL tests.
        manualChunks: {
          lemon: [
            "./src/components/lemon/LemonButton",
            "./src/components/lemon/LemonCard",
            "./src/components/lemon/LemonModal",
            "./src/components/lemon/LemonInput",
            "./src/components/lemon/LemonTextarea",
            "./src/components/lemon/LemonTag",
            "./src/components/lemon/LemonSelect",
            "./src/components/lemon/LemonDropdown",
            "./src/components/lemon/LemonTable",
            "./src/components/lemon/LemonToast",
          ],
        },
      },
    },
  },
  // The codegen output lives at src/generated/types.ts — no special
  // alias needed; it's just a relative import.
});
