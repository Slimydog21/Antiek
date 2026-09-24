import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { AdBorderMount } from "./components/ad/AdBorderMount";
import { NavRail } from "./shell/NavRail";
import { MascotStation } from "./shell/MascotStation";
import { Scene } from "./scene/Scene";
import { SceneChrome } from "./shell/SceneChrome";
import { Topbar } from "./components/navigation/Topbar";
import { LemonToastViewport, setToastNavigator } from "./components/lemon/LemonToast";
import { HotkeyHud } from "./components/hotkeys/HotkeyHud";
import { PrefixChip } from "./components/hotkeys/PrefixChip";
import { PanelLayout } from "./workspace/PanelLayout";
import { useWorkspace } from "./workspace/WorkspaceStore";
import { WindowsLayer } from "./components/windows/WindowsLayer";
import { useWorkspaceShortcuts } from "./workspace/shortcuts";
import { useWorkspaceHydration } from "./workspace/useWorkspaceHydration";

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
  // MS-01 — the keymap dispatcher, mounted once: the ONE owner of every
  // global key (the table is components/hotkeys/keymap.ts). The prefix
  // (ctrl+b), the ctrl+alt chords and the ⌘ combos fire from any route; the
  // scope rules keep typing, the Write editor and dialogs undisturbed.
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
      // relative + overflow-hidden: anything absolutely positioned inside the
      // frame is clipped by it and can never widen the page.
      className="relative h-screen w-screen bg-transparent text-ink dark:text-bright overflow-hidden"
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
      {/* No ambient brain here. BrainPresence (a 420px ghost brain anchored
          past the frame's corner) bled 77px sideways at 1280 and tinted the
          content; the mascot now appears only in hero, empty and error
          states, plus its station in the dock (design wave 3). */}

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
              Its inert coordinate layer remains mounted even when empty.
              SPR-09's one-line wiring,
              deferred to the AppShell owner so SPR-09 kept this file untouched. */}
          <WindowsLayer />
        </div>

        {/* SPR-06 M2 — navigation moved from the LEFT rail to a horizontal
            BOTTOM rail (orientation defaults to "bottom"), freeing the left
            edge so the working region above is full-width + symmetric. Four
            doors + Search + More, all shortcuts/accent/a11y preserved. */}
        <NavRail />
      </div>

      {/* SPR-12 M3 — the Mascot IS the floating project home. Mounted at shell
          level so it floats over the whole app (any route), not inside one
          surface. Single-click floats the project tree panel, double-click
          opens the project home, drag re-stations it (clamped on-screen).
          It seats itself in the dock's reserved station ([data-mascot-station]
          in NavRail), so it never covers the working area (design wave 3). */}
      <MascotStation />

      {/* SPR-07 — the one labelled house-ad slot (a single top rail since
          design wave 3; it was a four-edge border). Mounted ONCE here so it
          serves every lens with ONE code path. It is `position: fixed` and SETS
          the `--akb-border-inset-*` vars on the document root (default 0 in
          tokens.css), which the seam frame above reads as padding — so the
          working region shrinks into the reserved band while the slot paints
          in that band and never overlaps, clips, or shifts the working region. */}
      <AdBorderMount />

      {/* Toast viewport — single mount-point for the whole app */}
      <LemonToastViewport />

      {/* The key sheet (`?` or prefix+?). Mounted ONCE here; the uncontrolled
          instance self-subscribes to the HELP_TOGGLE window event the keymap
          dispatches, and lazy-loads the sheet itself (KeySheet.tsx) on first
          open. ESC closes it via LemonModal. */}
      <HotkeyHud />

      {/* MS-01 — the quiet "prefix armed" chip, shown while the keymap's
          prefix waits for its next key. */}
      <PrefixChip />
    </div>
  );
}

export default AppShell;
