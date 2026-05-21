import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "./design/tokens.css";
import App from "./App";

/**
 * S12 cutover flag.
 *
 * `VITE_ANTIEK_UI` chooses between the redesigned shell (`v2`,
 * default) and a hypothetical legacy fallback (`v1`). Today the
 * legacy shell is no longer present in the tree — its components
 * were retired in S4 + S5 + S6 + S10-light. Setting the flag to
 * "v1" currently still renders the v2 shell; the env var exists so
 * that a follow-up branch can re-introduce a legacy fallback if
 * rollback is needed during the cutover window per spec WP-12.3.
 *
 * The variable is logged once on mount so the operator can confirm
 * which build they're running.
 */
const uiVersion = (import.meta.env.VITE_ANTIEK_UI ?? "v2") as "v1" | "v2";
if (import.meta.env.DEV) {
  // eslint-disable-next-line no-console
  console.info(`[antiek] UI version: ${uiVersion}`);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
