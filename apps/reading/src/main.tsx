import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "./design/tokens.css";
import "./design/feel-focus.css";
import "./design/motion.css";
import App from "./App";
import AppLegacy from "./AppLegacy";
import { PostHogRoot } from "./lib/PostHogRoot";
import { retireLegacyWorkspaceSnapshots } from "./workspace/persistence";

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

// Run before React mounts: no route starter or effect can observe legacy
// descriptor state, and cleanup never becomes a render-time side effect.
retireLegacyWorkspaceSnapshots();
// Retire the unauthenticated tab-local collective cache without observing its bytes.
try {
  window.sessionStorage.removeItem("antiek.collective." + "unit_membership.v1");
} catch {
  // Storage may be disabled; retirement remains best-effort and read-free.
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PostHogRoot>
      <BrowserRouter>
        {uiVersion === "v1" ? <AppLegacy /> : <App />}
      </BrowserRouter>
    </PostHogRoot>
  </React.StrictMode>,
);
