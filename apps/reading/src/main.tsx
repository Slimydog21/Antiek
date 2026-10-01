import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "./design/tokens.css";
import "./design/motion.css";
import App from "./App";
import AppLegacy from "./AppLegacy";
import { PostHogRoot } from "./lib/PostHogRoot";
import { AppErrorBoundary } from "./lib/AppErrorBoundary";
import { installChunkLoadRecovery } from "./lib/chunkLoadRecovery";
import { RouteTitle } from "./lib/RouteTitle";
import { tabTreeHandle } from "./workspace/tabTreeHandle";

/**
 * S12 cutover flag.
 *
 * `VITE_ANTIEK_UI` chooses between the redesigned shell (`v2`, default,
 * renders <App />) and the legacy rollback (`v1`, renders <AppLegacy />
 * — the pre-S4 chrome). The legacy build is intentionally minimal: it
 * routes only the critical-path operator flows (Research + Wrestle +
 * Login) so the rollback is a tiny target if the new shell breaks in
 * production.
 *
 * To roll back: set `VITE_ANTIEK_UI=v1` in the production env, redeploy.
 * See `apps/reading/.env.example` and
 * `docs/ui_redesign_posthog/sprint_12_visual_regression_release.html`
 * §WP-12.3.
 */
const uiVersion = (import.meta.env.VITE_ANTIEK_UI ?? "v2") as "v1" | "v2";
if (import.meta.env.DEV) {
  // eslint-disable-next-line no-console
  console.info(`[antiek] UI version: ${uiVersion}`);
}

// P-05: a stale tab whose hashed chunks were replaced by a deploy reloads
// once per failed asset, then falls through to the boundary (never a loop).
installChunkLoadRecovery();

// Tabs persist to the active project's server row when lane B's routes
// answer (THREAD-CONTRACT §1.6); otherwise they stay in this session.
tabTreeHandle.bindOnLoad = true;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PostHogRoot>
      <BrowserRouter>
        {/* F-01: the one root boundary, covering both UI trees. Inside the
            router only so it can reset on pathname change; its fallback
            never depends on the router (see AppErrorBoundary.tsx). */}
        <AppErrorBoundary>
          {/* A-13: "<Mode name> · Antiek" per route, from MODE_TAXONOMY. */}
          <RouteTitle />
          {uiVersion === "v1" ? <AppLegacy /> : <App />}
        </AppErrorBoundary>
      </BrowserRouter>
    </PostHogRoot>
  </React.StrictMode>,
);
