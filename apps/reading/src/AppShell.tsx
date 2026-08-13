import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { AdBorderMount } from "./components/ad/AdBorderMount";
import { NavRail } from "./shell/NavRail";
import { PenguinMascot } from "./shell/PenguinMascot";
import { WernerIceCursorShell } from "./werner/WernerIceCursorShell";
import { Scene } from "./scene/Scene";
import BrainPresence from "./brand/BrainPresence";
import { SceneChrome } from "./shell/SceneChrome";
import { Topbar } from "./components/navigation/Topbar";
import { LemonToastViewport, setToastNavigator } from "./components/lemon/LemonToast";
import { HotkeyHud } from "./components/hotkeys/HotkeyHud";
import { PanelLayout } from "./workspace/PanelLayout";
import { useWorkspace } from "./workspace/WorkspaceStore";
import { WindowsLayer } from "./components/windows/WindowsLayer";
import { useWorkspaceShortcuts } from "./workspace/shortcuts";
import { useWorkspaceHydration } from "./workspace/useWorkspaceHydration";
import { useResearchNotifications } from "./hooks/useResearchNotifications";
import { useDocumentTitle } from "./hooks/useDocumentTitle";

/**
 * AppShell — the top-level chrome for the redesigned UI.
 *
 *   ┌────────────────────────────────────────────────────────┐
 *   │  Topbar — breadcrumbs · account                        │  ← full width
 *   ├────────────────────────────────────────────────────────┤
 *   │ ┌──────┬───────────────────────┬──────┐                │
 *   │ │ Dock │      Main slot        │ Dock │  ← PanelLayout │
 *   │ │  L   │     (route view)      │  R   │     (full      │
 *   │ │      │      + floating       │      │      width)    │
 *   │ └──────┴───────────────────────┴──────┘                │
 *   ├────────────────────────────────────────────────────────┤
 *   │  ⌂(igloo) ⌕   Research Read Write Speak     ⋯ More     │  ← bottom NavRail
 *   └────────────────────────────────────────────────────────┘
 *
 *   Layout (SPR-06 restructure):
 *     - The shell is a VERTICAL column. Topbar (44px) on top, the
 *       full-width working region in the middle, the NavRail (56px) as a
 *       horizontal BOTTOM rail. The rail moved off the LEFT so the working
 *       region consumes the full screen width symmetrically — the
 *       precondition for SPR-07's always-on, four-edge-symmetric ad border.
 *     - EDGE-RESERVATION SEAM: the column is wrapped in a frame that reads
 *       four CSS custom properties — `--akb-border-inset-{top,right,bottom,left}`
 *       — as padding. They default to 0 (see tokens.css), so THIS sprint
 *       changes no visible border; SPR-07 fills the seam by setting them to
 *       the border thickness. This is the single source of truth for the
 *       inset and the documented contract with SPR-07.
 *     - PanelLayout (left dock + main slot + right dock + floating) is
 *       unchanged and lives inside the full-width region.
 *     - LemonToastViewport mounted once at root (z=200).
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

  // herdr transfer P0-4 — toasts become navigation: clicking a targeted
  // toast jumps to the surface that produced it, then focuses the workspace
  // panel that lives there (focus is a no-op when the panel isn't in the
  // layout; starter panels open on route mount, hence the small delay).
  // The navigator bridge keeps LemonToast dependency-free (popout windows
  // mount its viewport without a router; they simply don't navigate).
  useEffect(() => {
    setToastNavigator((target) => {
      navigate(target.path);
      if (target.panelId) {
        const panelId = target.panelId;
        window.setTimeout(() => {
          useWorkspace.getState().focus(panelId);
        }, 60);
      }
    });
    return () => setToastNavigator(null);
  }, [navigate]);

  // S9 — hydrate the workspace from localStorage + URL ?ws= on every
  // route + investigation change. Layering order: global → route →
  // investigation → URL (one-shot). Writes the per-route /
  // per-investigation snapshot back to localStorage debounced at 250 ms.
  useWorkspaceHydration();

  // herdr transfer P1 — the sound visibility channel (suppressed while
  // watching; mute in Settings → Attention & sounds).
  useResearchNotifications();

  // herdr transfer P1 — the window title is a status surface (main SPA
  // only; popout windows own their own titles).
  useDocumentTitle();

  return (
    // EDGE-RESERVATION SEAM (SPR-06 M3) — the outer frame fills the viewport
    // and reserves the four edges via `--akb-border-inset-*` (tokens.css,
    // default 0). Padding here is the ONLY place the inset is applied, so
    // SPR-07 mounts its border by setting those vars + painting the padding
    // band; everything inside this frame already lives within the inset.
    // Zero inset today means no visible change. Documented in
    // docs/decisions/spr-06-edge-reservation-seam.md.
    <div
      data-akb-shell-frame
      // SPR-04 — the frame background is now TRANSPARENT (was bg-ice-2 /
      // dark:bg-space-2). The living mountainscape <Scene/> below paints the
      // z-0 backdrop for the whole app, and the glass working surfaces float
      // over it. The opaque ice/space surface is retained as the scene's OWN
      // bottom-most layer (ProceduralSky's sky gradient uses the same token
      // ramp), so there is no colour jump — the shell still reads ice by day,
      // space by night, but now it can MOVE. text tokens stay on the frame so
      // any chrome that doesn't set its own colour inherits readable ink.
      className="h-screen w-screen bg-transparent text-ink dark:text-bright overflow-hidden"
      style={{
        paddingTop: "var(--akb-border-inset-top)",
        paddingRight: "var(--akb-border-inset-right)",
        paddingBottom: "var(--akb-border-inset-bottom)",
        paddingLeft: "var(--akb-border-inset-left)",
        boxSizing: "border-box",
      }}
    >
      {/* SPR-04 — the living mountainscape. FIRST child so it sits at the very
          back (z-0), painted behind the column. It is `absolute inset-0 z-0
          pointer-events-none`, so it never captures input and the chrome /
          glass surfaces in the column below render ON TOP of it. Procedural
          clouds + wind + snow run always-on; Krea art refreshes the sky on
          mood change; it freezes to one frame under reduced-motion and pauses
          on a hidden tab. (It lives INSIDE the seam frame so the ad border's
          reserved band, when SPR-07 lights it up, frames the scene too.) */}
      <Scene />
      <BrainPresence />

      {/* Vertical column: topbar · full-width working region · bottom rail.
          The working region carries NO left gutter — it spans the full
          width between the (zero-inset) left/right seam edges, symmetric.
          `relative` so it stacks above the absolute z-0 scene. */}
      <div className="relative h-full w-full flex flex-col">
        <Topbar />
        <div className="relative flex-1 min-h-0 min-w-0">
          {/* SceneChrome (SPR-04 zone 3) wraps the route view as the
              main slot: per-workflow action bar + in-scene tabs sit
              above the surface, while the Zustand panel workspace
              continues to dock left/right/bottom + float around it.
              The mode still mounts as a panel exactly as before. */}
          <PanelLayout mainSlot={<SceneChrome>{children}</SceneChrome>} />
          {/* SPR-09 — transparent workspace windows float over the working
              region + scene (this container is `relative` so the layer's
              absolute inset-0 anchors here, between Topbar and the NavRail).
              Renders nothing until a window opens. SPR-09's one-line wiring,
              deferred to the AppShell owner so SPR-09 kept this file untouched. */}
          <WindowsLayer />
        </div>

        {/* SPR-06 M2 — navigation moved from the LEFT rail to a horizontal
            BOTTOM rail (orientation defaults to "bottom"), freeing the left
            edge so the working region above is full-width + symmetric. Four
            doors + Search + More, all shortcuts/accent/a11y preserved. */}
        <NavRail />
      </div>

      {/* SPR-12 M3 — the Penguin mascot IS the floating project home, now an
          AUTONOMOUS WADDLER (SPR-06 M5): it roams the viewport on its own,
          bounded + reduced-motion-safe. Mounted at shell level so it floats
          over the whole app (any route), not inside one surface. Single-click
          floats the project tree panel, double-click opens the project home,
          drag moves it (clamped on-screen). This supersedes the old NavRail
          "+ project / Project tree" button — the tree is reached through the
          Penguin. (It sits OUTSIDE the seam frame on purpose: a free agent
          roaming the whole window, not a chrome element constrained by the
          ad-border inset.) */}
      <PenguinMascot />

      {/* WERNER-ICE SPR-13 — live bait cursor + html cursor policy (z-59). */}
      <WernerIceCursorShell />

      {/* SPR-07 — the always-on, four-edge "Times-Square" ad border. Mounted
          ONCE here so it wraps every lens — Read / Research / Write / Speak —
          with ONE code path. Its DOM position inside this frame is irrelevant
          to layout: the border itself is `position: fixed` (inset-0), and it
          SETS the `--akb-border-inset-*` vars on the document root (default 0
          in tokens.css), which the seam frame `div` above inherits and reads as
          padding — so the working region shrinks into the reserved band while
          the fixed border paints in that band and never overlaps, clips, or
          shifts the working region. */}
      <AdBorderMount />

      {/* Toast viewport — single mount-point for the whole app */}
      <LemonToastViewport />

      {/* SPR-08 — the keyboard cheat-sheet. Mounted ONCE here so a single
          uncontrolled instance self-subscribes to the HELP_TOGGLE window event
          (fired by `?` in shortcuts.ts, guarded so it never fires while
          typing); ESC closes it via LemonModal's focus trap. */}
      <HotkeyHud />
    </div>
  );
}

export default AppShell;
