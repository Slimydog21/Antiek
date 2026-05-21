import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
      "/health": "http://localhost:8000",
      "/events": "http://localhost:8000",
      "/trajectory": "http://localhost:8000",
      // Magic-link auth (H6): both /auth/request/me and the
      // /auth/callback redirect need to be same-origin with the
      // page or the browser drops Set-Cookie.
      "/auth": "http://localhost:8000",
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
  // The codegen output lives at src/generated/types.ts — no special
  // alias needed; it's just a relative import.
});
