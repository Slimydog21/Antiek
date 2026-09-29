import type { IncomingMessage } from "node:http";
import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

// Use the literal loopback address for the proxy target. Newer Node releases
// may resolve `localhost` to IPv6 first while uvicorn listens on IPv4, leaving
// browser fetches hanging even though direct navigation succeeds.
// The port is overridable so an e2e harness can boot its OWN backend on a
// free port instead of racing the operator's live one — which also keeps the
// harness off the live DuckDB writer lock (single-writer invariant: two
// uvicorns on one graph file is exactly the conflict db_lock exists to stop).
// An empty value counts as unset. A whitespace-only value is NOT trimmed or
// defaulted: it is used verbatim as the proxy target (known open item F-06).
const API_TARGET = process.env.ANTIEK_DEV_API_TARGET || "http://127.0.0.1:8000";

/**
 * The WebSocket target for an HTTP API target: http→ws, https→wss, host and
 * port unchanged. /ws MUST follow ANTIEK_DEV_API_TARGET: a hardcoded
 * ws://127.0.0.1:8000 made every isolated harness silently stream the
 * operator's live event bus while its HTTP went to the harness backend (A-19).
 */
export function wsTargetFor(apiTarget: string): string {
  // Schemes are case-insensitive; emit the canonical lower-case one.
  return apiTarget.replace(/^https?:/i, (scheme) =>
    scheme.toLowerCase() === "https:" ? "wss:" : "ws:",
  );
}

/**
 * Proxy `bypass` for prefixes that are BOTH an API route family and an SPA
 * route. A browser navigation (a GET/HEAD whose Accept includes text/html)
 * returns the URL untouched, so Vite's SPA fallback serves index.html and a
 * hard reload of /sources renders the app instead of FastAPI's
 * {"detail":"Not Found"} (A-19). Everything else (fetch() defaults to the wildcard Accept;
 * our API helpers never ask for text/html) returns undefined and
 * is proxied. Cloudflare Pages does the same split in production, where the
 * API is a different origin and the question never arises.
 *
 * Why Accept-header routing and not a port split or an /api prefix: those
 * are backend + edge (Caddy @api_routes) contract changes. Replace this
 * bypass when the API moves under a single /api prefix; delete it then.
 */
export function spaNavigationBypass(
  req: Pick<IncomingMessage, "method" | "headers" | "url">,
): string | undefined {
  if (req.method !== "GET" && req.method !== "HEAD") return undefined;
  // Media types are case-insensitive (RFC 9110 §8.3.1). Known limit: q-values
  // are not parsed, so an explicit "text/html;q=0" still counts as HTML.
  if (!req.headers.accept?.toLowerCase().includes("text/html")) return undefined;
  return req.url;
}

// Vite's string shorthand is { target, changeOrigin: true }; keep that.
const api = (opts: Partial<ProxyOptions> = {}): ProxyOptions => ({
  target: API_TARGET,
  changeOrigin: true,
  ...opts,
});
// For a prefix that also names an SPA route (Vite matches url.startsWith).
const apiSharedWithSpa = () => api({ bypass: spaNavigationBypass });

// In dev, the Python substrate runs at http://localhost:8000. We could
// either proxy here or rely on CORS on the backend. We do BOTH — proxy
// is the primary path so no cross-origin happens in the browser, CORS
// is the fallback in case the operator runs the frontend somewhere
// other than this Vite dev server.
//
// We proxy each prefix individually rather than blanket-proxying — keeps
// the dev path explicit. Prefixes WITHOUT the SPA bypass stay proxied for
// navigations too: /auth/callback and /auth/dev-login are navigations the
// API must answer. vite.config.test.ts derives from src/App.tsx which
// prefixes shadow an SPA route and fails if the bypass set drifts.

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": api(),
      "/api": api(),
      "/events": api(),
      "/trajectory": api(),
      // The cascade plan/launch/session surface (cascade_routes.py, prefix
      // /research). The Research-entry cascade mode + the DRW monitor both
      // call it; without this proxy a dev drive can't reach the backend.
      "/research": api(),
      "/styles": api(),
      "/artifacts": api(),
      // Metadata-only Library catalog (GET /library?…, api/libraryCatalog.ts).
      // Keep this explicit rather than using a blanket proxy so body-serving
      // routes remain independently reviewed. Also the SPA's /library and
      // /library/browse.
      "/library": apiSharedWithSpa(),
      // Anti-Ek dogfood smoke: BookReader + Sources need a same-origin proxy
      // or SPA HTML is returned and JSON.parse fails.
      "/books": api(),
      // POST /sources/upload + source listing (lib/sourceUploadApi.ts). Also
      // the SPA's /sources page.
      "/sources": apiSharedWithSpa(),
      // Investigation create/list (lib/api.ts). Also the SPA's /investigations.
      "/investigations": apiSharedWithSpa(),
      "/chunks": api(),
      // Write blocks/folders/sections (modes/Write/writeApi.ts). Also the
      // SPA's /write and /write/:deliverableId.
      "/write": apiSharedWithSpa(),
      // Notebook CRUD + content (lib/api.ts, modes/Notebook). Also the SPA's
      // /notebooks list (the editor lives at /notebook/:id, not shadowed).
      "/notebooks": apiSharedWithSpa(),
      // Magic-link auth (H6): both /auth/request/me and the
      // /auth/callback redirect need to be same-origin with the
      // page or the browser drops Set-Cookie. No bypass: the callback is a
      // navigation the API must answer.
      "/auth": api(),
      // Owner-private account memory (account_memory_routes.py). The panel
      // at /memory reads and corrects facts here; same-origin in dev so the
      // session cookie travels and no CORS preflight sits on the POST.
      "/account": api(),
      // Mountain Shell SPR-02 — the Krea scene-art proxy
      // (krea_routes.py). Same-origin in dev so the browser never sees
      // the server-held KREA_API_TOKEN and no CORS is involved.
      "/krea": api(),
      // Own Your Mind P0 (explain_routes.py + ops_routes.py): the
      // provenance + ops surfaces. Same explicit-prefix discipline as the
      // routes above — each new backend prefix gets a reviewed line here.
      "/claims": api(),
      "/syntheses": api(),
      "/docs": api(),
      "/ops": api(),
      // /ws/events: same backend as HTTP, derived from ANTIEK_DEV_API_TARGET.
      "/ws": {
        target: wsTargetFor(API_TARGET),
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
