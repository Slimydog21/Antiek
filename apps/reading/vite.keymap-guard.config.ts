import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const books = ["a", "b", "c"].map((id) => ({
  document_id: `guard-${id}`, title: `Guard book ${id.toUpperCase()}`, author: "D2 fixture",
  servability: "public_domain", servable_full_text: true, page_count: 1,
  cover_uri: null, ip_holder_id: null, taken_down: false,
  pagination_scheme: "text", provenance: "D2 keyboard behavior fixture", license_basis: "public_domain",
  toc: [{ title: "Fixture chapter", page_index: 0, level: 0 }],
}));

/** Network data only. The entry, router, shell, handlers and surfaces are the app's. */
export default defineConfig({
  plugins: [react(), {
    name: "d2-keymap-network-fixtures",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url ?? "/", "http://fixture");
        const path = url.pathname;
        if (req.headers.accept?.includes("text/html") || /^\/(@|src\/|node_modules\/|scripts\/)/.test(path)
          || /\.(js|ts|tsx|css|svg|png|ico|woff2?)(\?|$)/.test(path)) return next();
        let body: unknown;
        let status = 200;
        if (path === "/auth/me") body = { user_id: "d2-guard", email: "guard@example.test", auth_method: "fixture" };
        else if (path === "/books") body = { books, count: books.length };
        else if (/^\/books\/guard-[abc]$/.test(path)) body = books.find((b) => path.endsWith(b.document_id));
        else if (/^\/books\/guard-[abc]\/(owner-full-text|full-text)$/.test(path)) body = {
          document_id: path.split("/")[2], servable: true, servability: "public_domain",
          full_text: "Fixture chapter\n\nA keyboard action must change the visible app, not a counter.",
          snippet: null, title: "Guard book", author: "D2 fixture", reason: "public_domain",
          tier: null, ad_eligible: false, canonical_url: null, license: null,
        };
        else if (path.includes("anchor-map")) body = { chunks: [], coordinate_space: "unicode-nfc-v1" };
        else if (path.includes("anchors")) body = { anchors: [] };
        else if (path === "/projects") body = { projects: [{ project_id: "default", name: "Guard project" }] };
        else if (path === "/investigations") body = { investigations: [] };
        else if (path === "/documents") body = { documents: [] };
        else if (path === "/speak/projects") body = { projects: [] };
        else if (path === "/krea/status") body = {
          enabled: false, key_present: false, kill_switch: false, gate_verdict: "no_key", reasons: ["no_key"],
          budget: { spent_today: 0, cap: 0, remaining: 0 }, rate_window: { occupancy: 0, max: 0, window_s: 60 },
          cache: { entries: 0, max_entries: 0 }, last_success_at: null, failure_counts: {}, failures: [],
        };
        else if (path.startsWith("/krea/")) body = { art: null, enabled: false };
        else { body = { detail: `No fixture for ${path}` }; status = 404; }
        res.writeHead(status, { "Content-Type": "application/json" });
        res.end(JSON.stringify(body));
      });
    },
  }],
  server: { host: "127.0.0.1", port: 5196, strictPort: true },
});
