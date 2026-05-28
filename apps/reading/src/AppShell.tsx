import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { NavRail } from "./shell/NavRail";
import { PenguinMascot } from "./shell/PenguinMascot";
import { SceneChrome } from "./shell/SceneChrome";
import { Topbar } from "./components/navigation/Topbar";
import { LemonToastViewport } from "./components/lemon/LemonToast";
import { PanelLayout } from "./workspace/PanelLayout";
import { useWorkspaceShortcuts } from "./workspace/shortcuts";
import { useWorkspaceHydration } from "./workspace/useWorkspaceHydration";

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

  // S9 — hydrate the workspace from localStorage + URL ?ws= on every
  // route + investigation change. Layering order: global → route →
  // investigation → URL (one-shot). Writes the per-route /
  // per-investigation snapshot back to localStorage debounced at 250 ms.
  useWorkspaceHydration();

  return (
    <div className="h-screen w-screen flex bg-ice-2 dark:bg-space-2 text-ink dark:text-bright overflow-hidden">
      {/* Always-visible icon rail */}
      <NavRail />

      {/* Main column: topbar + panel layout */}
      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar />
        <div className="flex-1 min-h-0">
          {/* SceneChrome (SPR-04 zone 3) wraps the route view as the
              main slot: per-workflow action bar + in-scene tabs sit
              above the surface, while the Zustand panel workspace
              continues to dock left/right/bottom + float around it.
              The mode still mounts as a panel exactly as before. */}
          <PanelLayout mainSlot={<SceneChrome>{children}</SceneChrome>} />
        </div>
      </div>

      {/* SPR-12 M3 — the Penguin mascot IS the floating project home.
          Mounted at shell level so it floats over the whole app (any
          route), not inside one surface. Single-click floats the project
          tree panel, double-click opens the project home, drag moves it
          (clamped on-screen), idle waddle/wander (reduced-motion-safe).
          This supersedes the old NavRail "+ project / Project tree"
          button — the tree is now reached through the Penguin. */}
      <PenguinMascot />

      {/* Toast viewport — single mount-point for the whole app */}
      <LemonToastViewport />
    </div>
  );
}

export default AppShell;
