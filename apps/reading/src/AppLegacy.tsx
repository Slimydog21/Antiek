import { lazy, Suspense } from "react";
import { Route, Routes, Navigate, Outlet, useLocation } from "react-router-dom";

import ResearchWorkstation from "./modes/ResearchWorkstation";
import WrestleApp from "./modes/WrestleApp";
import Login from "./modes/Login";
import { PanelLayout } from "./workspace/PanelLayout";
import { AuthProvider, useAuth } from "./lib/auth";

const Settings = lazy(() => import("./modes/Settings"));

/**
 * AppLegacy — the v1 / pre-S4 chrome.
 *
 * S12 acceptance: production build with `VITE_ANTIEK_UI=v1` renders
 * the old shell (rollback path; sprint_12_visual_regression_release.html
 * §WP-12.3). The new chrome (AppShell + NavRail + Topbar) is hidden;
 * critical routes retain one route-local panel layout, without top chrome
 * (HeaderBar, the pre-redesign top bar, was a deprecated no-op and is
 * now deleted — Q7 dead-UI sweep).
 *
 * This shell ships in the bundle for one sprint after cutover. If
 * S13 (legacy retirement) has shipped, this file should be deleted.
 *
 * Scope: Research, Wrestle and the Settings needed to connect an owner
 * model are routed here. The fuller pre-S4 App.tsx wired every route through
 * HeaderBar; we deliberately don't reconstruct the entire pre-S4
 * routing graph because:
 *
 *   (a) the panel system surfaces all routes correctly under v2
 *   (b) v1 is a rollback safety net — if the operator's hitting
 *       AppLegacy, the new shell is broken and they're using this
 *       just long enough to ship a fix
 *   (c) reconstructing every legacy mode wrapper would duplicate
 *       a lot of code that's all going away in S13 anyway
 *
 * Research, Wrestle, Settings and Login cover the critical-path operator
 * flows: investigations, document review and owner model setup.
 * Everything else 404s with a clear "v1 doesn't include this route —
 * flip back to v2 to access" panel.
 */
export default function AppLegacy() {
  return (
    <AuthProvider>
      <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2 text-ink dark:text-bright">
        <main className="flex-1 min-h-0 overflow-auto">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<LegacyWorkspace />}>
              <Route path="/" element={<ResearchWorkstation />} />
              <Route
                path="/inv/:investigationId"
                element={<ResearchWorkstation />}
              />
              <Route path="/wrestle" element={<WrestleApp />} />
              <Route path="/wrestle/:documentId" element={<WrestleApp />} />
              <Route path="/settings" element={
                <Suspense fallback={<div role="status" className="p-8 text-sm font-mono">Loading settings…</div>}>
                  <Settings />
                </Suspense>
              } />
            </Route>
            <Route path="*" element={<LegacyMissingRoute />} />
          </Routes>
        </main>
      </div>
    </AuthProvider>
  );
}

function LegacyWorkspace() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") {
    return <div role="status" className="p-8 text-sm font-mono">Loading…</div>;
  }
  if (state.status === "unauthenticated") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <PanelLayout mainSlot={<Outlet />} />;
}

function LegacyMissingRoute() {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-3">
        <h1 className="text-xl font-serif text-ink dark:text-bright">
          Not available in v1 rollback
        </h1>
        <p className="text-sm text-ink-soft dark:text-starlight">
          This route ships with the v2 (redesigned) shell. Set{" "}
          <code className="font-mono">VITE_ANTIEK_UI=v2</code> to access
          it.
        </p>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          See <code>apps/reading/.env.example</code> and the S12 spec.
        </p>
      </div>
    </div>
  );
}
