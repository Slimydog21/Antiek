import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { NavRail } from "./components/navigation/NavRail";
import { Topbar } from "./components/navigation/Topbar";
import { LemonToastViewport } from "./components/lemon/LemonToast";
import { PanelLayout } from "./workspace/PanelLayout";
import { useWorkspaceShortcuts } from "./workspace/shortcuts";

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

      {/* Toast viewport — single mount-point for the whole app */}
      <LemonToastViewport />
    </div>
  );
}

export default AppShell;
