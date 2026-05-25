import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";

import { NavRail } from "./components/navigation/NavRail";
import { ProductsLauncher } from "./components/navigation/ProductsLauncher";
import { Topbar } from "./components/navigation/Topbar";
import { LemonToastViewport } from "./components/lemon/LemonToast";
import { PanelLayout } from "./workspace/PanelLayout";
import { useWorkspace } from "./workspace/WorkspaceStore";
import { useWorkspaceShortcuts } from "./workspace/shortcuts";
import { useWorkspaceHydration } from "./workspace/useWorkspaceHydration";
import { useActiveWorkflow } from "./shell/activeWorkflow";
import { workflowForRoute } from "./shell/workflowTaxonomy";

const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";

/**
 * AppShell — the top-level chrome for the redesigned UI.
 *
 *   ┌──────┬──────────────────────────────────────────────────┐
 *   │      │  Topbar — breadcrumbs · ⌘K · account             │
 *   │ Nav  ├──────────────────────────────────────────────────┤
 *   │ Rail │ ┌──────┬─────────────────┬──────┐                │
 *   │      │ │ Dock │   Main slot     │ Dock │  ← PanelLayout │
 *   │ ⌂ ⏍ │ │  L   │   (route view)  │  R   │                │
 *   │ ❒ 🜘 │ │      │   + floating    │      │                │
 *   │      │ └──────┴─────────────────┴──────┘                │
 *   └──────┴──────────────────────────────────────────────────┘
 *
 *   Layout:
 *     - NavRail   60px, always visible, outside the dock system
 *     - Topbar    44px, breadcrumbs + search + account
 *     - PanelLayout (left dock + main slot + right dock + floating)
 *     - LemonToastViewport mounted once at root (z=200)
 *
 * Wraps children as the main slot — the same children-shape pattern the
 * existing AuthenticatedRoutes uses. Once App.tsx integrates AppShell,
 * the wrap looks like:
 *
 *     <AppShell>
 *       <CommandPalette />
 *       <AISidecar />
 *       <Routes>... all routes ...</Routes>
 *     </AppShell>
 *
 * Per-route panel starters opt in via the route's own component using
 * <PanelHost starters={[…]}> — AppShell does NOT auto-open panels.
 * The operator's last-used panel layout is restored in S9.
 */
type Props = {
  children: ReactNode;
};

export function AppShell({ children }: Props) {
  // S8 — mount the keyboard shortcut handler once at the shell level.
  // Lives here (not lower) so ⌘K, ⌘B, ⌘/, ⌘[, ⌘], G+I etc. fire from
  // any route. The handler ignores key events when the active element
  // is editable, so the operator can still type freely.
  const navigate = useNavigate();
  useWorkspaceShortcuts(navigate);

  // Four-workflow IA (SPR-03): keep the active workflow in sync with the
  // route, so the rail highlight + the content tree follow navigation — a
  // deep link or back/forward sets the workflow without a rail click. On a
  // shared/operator route (workflowForRoute → null) we keep the last
  // workflow, so the tree still shows meaningful content.
  const { pathname } = useLocation();
  const setActiveWorkflow = useActiveWorkflow((s) => s.set);
  useEffect(() => {
    const w = workflowForRoute(pathname);
    if (w) setActiveWorkflow(w);
  }, [pathname, setActiveWorkflow]);

  // S9 — hydrate the workspace from localStorage + URL ?ws= on every
  // route + investigation change. Layering order: global → route →
  // investigation → URL (one-shot). Writes the per-route /
  // per-investigation snapshot back to localStorage debounced at 250 ms.
  useWorkspaceHydration();

  // Portfolio-shell IA: the content tree is the persistent second
  // column, not just a ⌘B afterthought. Open it once on first mount if
  // nothing has opened it yet (runs after hydration so a restored layout
  // wins). The operator can still close it with ⌘B for the session.
  const treeBootstrapped = useRef(false);
  useEffect(() => {
    if (treeBootstrapped.current) return;
    treeBootstrapped.current = true;
    const ws = useWorkspace.getState();
    if (!ws.panels[PROJECT_TREE_PANEL_ID]) {
      ws.open(
        "ProjectTree",
        {},
        { mode: "docked-left", title: "Project", id: PROJECT_TREE_PANEL_ID },
      );
    }
  }, []);

  return (
    <div className="h-screen w-screen flex bg-ice-2 dark:bg-space-2 text-ink dark:text-bright overflow-hidden">
      {/* Always-visible icon rail */}
      <NavRail />

      {/* Main column: topbar + panel layout */}
      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar />
        <div className="flex-1 min-h-0">
          <PanelLayout mainSlot={children} />
        </div>
      </div>

      {/* Products launcher overlay — opened from the rail's ⊞ button */}
      <ProductsLauncher />

      {/* Toast viewport — single mount-point for the whole app */}
      <LemonToastViewport />
    </div>
  );
}

export default AppShell;
