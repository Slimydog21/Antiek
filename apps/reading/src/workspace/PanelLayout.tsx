import { registerKeyboardOwner } from "./keyboardOwnership";
import { Suspense, lazy, useCallback, useContext, useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { UNSAFE_LocationContext, useInRouterContext } from "react-router-dom";

import { toast } from "../components/lemon/LemonToast";
import { LoadingState } from "../components/states";
import { radius } from "../design/tokens";
import RightPaneForMode from "./RightPaneForMode";
import { COMPANION_PANEL_ID } from "./companionVisibility";
import { mothershipForPath } from "./mothershipForPath";
import { DOCUMENT_PANEL_ID } from "./documentPanel";
import { PanelLayoutPanel } from "./PanelLayoutPanel";
import ProjectTreeOverlay from "./ProjectTreeOverlay";
import { useWorkspace } from "./WorkspaceStore";
import { escOverlayOpen } from "./escapeOverlay";
import { isTextEditing } from "./shortcuts";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";
import { useViewportTier } from "./useViewportTier";
import { WRITE_OUTLINE_PANEL_ID } from "./writeOutlineStore";
import { usePaneFlowFrame } from "./PaneFlowLayout";
import { CORE_PANE, COMPANION_PANE } from "./paneFlowGeometry";

// The document tab strip (D6) and the tab-tree model it renders load on
// first show, not with the entry chunk, which has a hard gzip budget (npm
// run build:check). The right pane's heavy halves load lazily inside
// RightPaneForMode.
const DocumentTabStrip = lazy(() =>
  import("./DocumentTabStrip").then((m) => ({ default: m.DocumentTabStrip })),
);

/** The strip's own loading skeleton, drawn while its chunk loads, so the
 *  strip lands in place with no layout shift. The same markup as the loaded
 *  strip's loading state. */
function DocumentStripFallback() {
  return (
    <div data-document-strip className="shrink-0 border-b border-hairline bg-ice-1 dark:bg-charcoal-1">
      <LoadingState variant="inline" shape="strip" rows={3} label="Opening your tabs" />
    </div>
  );
}

/**
 * PanelLayout — the orchestrator.
 *
 * Lays out three vertical zones + a bottom strip beneath the main slot:
 *
 *   ┌──────────┬───────────────────────────┬──────────┐
 *   │          │                           │          │
 *   │  LEFT    │       MAIN SLOT           │  RIGHT   │
 *   │  DOCK    │   (caller-supplied; the   │  DOCK    │
 *   │          │    route Outlet, usually) │          │
 *   │          │   + FLOATING LAYER over   │          │
 *   │          │     the main slot         │          │
 *   │          ├───────────────────────────┤          │
 *   │          │       BOTTOM DOCK         │          │
 *   │          │ (Chat-style surfaces)     │          │
 *   └──────────┴───────────────────────────┴──────────┘
 *
 * Each dock animates its width/height to 0 when empty so the main slot
 * gets the full viewport when there are no docked panels. The bottom
 * dock is operator-resizable via a top-edge grab handle.
 *
 * S5 introduces the bottom dock for the Chat panel; the same primitive
 * is available to any panel-kind that opts into mode="docked-bottom".
 */
type Props = { mainSlot: ReactNode };

const DOCK_WIDTH = 320;

/**
 * The inset preset's outer gap (C2): the scene background shows through it
 * around and between the two panes. A named layout constant owned here (like
 * DOCK_WIDTH), not a colour — the colour tokens stay the three-layer gate's.
 */
const INSET_GAP = 12;

/**
 * The docked preset's mounts of what the inset's right pane IS: the
 * companion and the Write outline open as right-dock panels there. In the
 * inset the pane itself renders them (RightPaneForMode), so the dock inside
 * it skips these two; rendering both drew the outline twice after a preset
 * round trip (B3-2).
 */
const PANE_CONTENT_PANEL_IDS: ReadonlySet<string> = new Set([COMPANION_PANEL_ID, WRITE_OUTLINE_PANEL_ID]);

/**
 * The inset's right pane at tier md (768–1023 px, an Omarchy half screen on
 * a 1920 px display): it narrows instead of vanishing, so the cockpit keeps
 * both panes (DESIGN-MODEL "Pane behaviour, ratified from A1b", forensic
 * T10). From lg up it keeps its token width (DOCK_WIDTH).
 */
const RIGHT_PANE_MD_WIDTH = 280;

export function PanelLayout({ mainSlot }: Props) {
  const dockLeftIds = useWorkspace((s) => s.dockLeftIds);
  const dockRightIds = useWorkspace((s) => s.dockRightIds);
  const dockBottomIds = useWorkspace((s) => s.dockBottomIds);
  const floatingIds = useWorkspace((s) => s.floatingIds);
  const dockBottomHeight = useWorkspace((s) => s.dockBottomHeight);
  const setDockBottomHeight = useWorkspace((s) => s.setDockBottomHeight);
  const layoutPreset = useWorkspace((s) => s.layoutPreset);
  const fullscreenPane = useWorkspace((s) => s.fullscreenPane);
  const focusedPane = useWorkspace((s) => s.focusedPane);
  const setFocusedPane = useWorkspace((s) => s.setFocusedPane);
  const setFullscreenPane = useWorkspace((s) => s.setFullscreenPane);
  const reduceMotion = usePrefersReducedMotion();
  // The strip renders nothing without a router, so neither does its fallback.
  const inRouter = useInRouterContext();
  const tier = useViewportTier();
  const projectTreeOverlay = tier === "md" && dockLeftIds.includes("shortcuts:projecttree");
  // What the right pane holds follows the route's mothership (the outline in
  // writing, the agents elsewhere), so its name does too. Read through the
  // router's location context: PanelLayout also renders without a router.
  const location = useContext(UNSAFE_LocationContext)?.location;
  const writing = location ? mothershipForPath(location.pathname, location.search) === "writing" : false;
  const coreFlow = usePaneFlowFrame(CORE_PANE);
  const companionFlow = usePaneFlowFrame(COMPANION_PANE);
  const paneZoom = useWorkspace((s) => s.paneZoom);

  // S11 (the docked preset) — at tier "lg" the two side docks can't both be
  // visible; if both have panels we collapse the right one (operator can
  // flip via kebab). At tier "md" docks disappear entirely — the panels
  // would still render but the dock widths drop to 0 so they collapse out
  // of view. The inset preset sizes its panes below instead: its right dock
  // lives inside the companion pane, which never collapses.
  const dockSide = (side: "left" | "right", count: number): number => {
    if (count === 0) return 0;
    // Cockpit fullscreen in the docked preset collapses every dock: the main
    // slot fills the cockpit (the same "hide the companions" gesture the
    // inset preset performs by hiding one pane).
    if (layoutPreset === "docked" && fullscreenPane) return 0;
    if (tier === "sm" || tier === "md") return 0;
    if (tier === "lg") {
      if (side === "right" && dockLeftIds.length > 0 && dockRightIds.length > 0) {
        return 0;
      }
    }
    return DOCK_WIDTH;
  };

  const dockTransition = reduceMotion
    ? "transition-none"
    : "transition-[width] duration-150 ease-out";

  // S11 acceptance: at tier `lg`, if both docks have content the
  // right dock auto-collapses. Surface this as a toast the first
  // time it happens after a viewport-tier crossing into lg so the
  // operator understands the visual change.
  const prevTierRef = useRef(tier);
  useEffect(() => {
    if (
      layoutPreset === "docked" &&
      prevTierRef.current !== "lg" &&
      tier === "lg" &&
      dockLeftIds.length > 0 &&
      dockRightIds.length > 0
    ) {
      toast.info(
        "Tight viewport — right dock auto-collapsed. Toggle via the right panel's kebab.",
      );
    }
    prevTierRef.current = tier;
  }, [tier, dockLeftIds.length, dockRightIds.length, layoutPreset]);

  // Pointer-event-based vertical resize of the bottom dock. Every hook in
  // this component runs before the tier `sm` early return below: a hook
  // after it changes the hook count when the viewport crosses 768 px, and
  // React throws ("Rendered more hooks than during the previous render").
  const startRef = useRef<{ y: number; h: number } | null>(null);
  const onResizeDown = useCallback(
    (e: React.PointerEvent) => {
      (e.target as Element).setPointerCapture(e.pointerId);
      startRef.current = { y: e.clientY, h: dockBottomHeight };
    },
    [dockBottomHeight],
  );
  const onResizeMove = useCallback(
    (e: React.PointerEvent) => {
      if (!startRef.current) return;
      const dy = startRef.current.y - e.clientY; // up = grow
      setDockBottomHeight(startRef.current.h + dy);
    },
    [setDockBottomHeight],
  );
  const onResizeUp = useCallback(() => {
    startRef.current = null;
  }, []);

  // Cockpit fullscreen restore (C3): "Esc restores from any focus"
  // (DESIGN-MODEL §2), so the listener is on the document, not the layout
  // root; with focus on <body> a root-scoped handler never saw the key. It
  // exists only while a pane is fullscreen: an overlay's own key, the one
  // sanctioned exception to the one-dispatcher rule (never a global
  // binding, never a keymap row). One Esc reaches exactly one handler: a
  // key an element claimed first (defaultPrevented), pressed while typing,
  // pressed inside a dialog, or pressed while any transient overlay is open
  // (a menu, a listbox, a modal, the FloatMenu, the tab-tree popover: see
  // escapeOverlay.ts) stays theirs; that Esc closes the overlay and the
  // next one restores the panes.
  useEffect(() => {
    if (!fullscreenPane && !paneZoom) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      const target = e.target instanceof Element ? e.target : null;
      if (target && isTextEditing(target)) return;
      if (target?.closest("[role='dialog'], [role='alertdialog']")) return;
      if (escOverlayOpen()) return;
      if (paneZoom) {
        if (!e.repeat) coreFlow.restoreZoom(e);
      }
      else setFullscreenPane(null);
    };
    const removeKeyboardOwner = registerKeyboardOwner(document, {
      id: "pane.fullscreen.escape", scope: "overlay",
      eligible: (e) => e.key === "Escape" && !e.defaultPrevented && !(e.target instanceof Element && (isTextEditing(e.target) || e.target.closest("[role=dialog], [role=alertdialog]"))) && !escOverlayOpen(),
    }, onKeyDown);
    return () => removeKeyboardOwner();
  }, [fullscreenPane, setFullscreenPane, paneZoom, coreFlow.restoreZoom]);

  // Tier `sm` (< 768px) is the phone layout: one column, the route view
  // alone and scrollable. The docks and floating panels stay out of it (a
  // 320px dock cannot fit), and there is no "use a larger screen" banner:
  // the shell around it (5-key dock, quiet header) is the phone design.
  if (tier === "sm") {
    return <div data-cockpit-content tabIndex={-1} className="h-full w-full overflow-auto">{mainSlot}</div>;
  }

  const inset = layoutPreset === "omarchy-inset";

  // Fullscreen in the docked preset hides the bottom dock too (dockSide
  // already zeroes the side docks); the default state is untouched.
  const hideBottomDock = !inset && fullscreenPane !== null;

  // The centre column is IDENTICAL in both presets — one JSX value, so the
  // inset preset cannot drift from the docked one. The document tab strip
  // (D6) mounts here once, so the inset left pane and the docked main
  // surface share it (router-guarded: it renders nothing without a Router
  // context).
  const centreColumn = (
    <div className="flex-1 min-w-0 flex flex-col">
      <Suspense fallback={inRouter ? <DocumentStripFallback /> : null}>
        <DocumentTabStrip />
      </Suspense>
      <main data-cockpit-content tabIndex={-1} className="flex-1 min-w-0 relative overflow-hidden">
        {/* Underlying mainSlot — the route content (the document tabs'
            tabpanel while the strip is mounted) */}
        <div id={DOCUMENT_PANEL_ID} className="absolute inset-0 overflow-auto">{mainSlot}</div>

        {/* Floating layer — pointer-events:none container, panels opt back in */}
        <div className="absolute inset-0 pointer-events-none">
          {floatingIds.map((id) => (
            <div key={id} className="pointer-events-auto">
              <PanelLayoutPanel id={id} />
            </div>
          ))}
        </div>
      </main>

      {/* BOTTOM DOCK — kept mounted while fullscreen hides it */}
      {dockBottomIds.length > 0 && (
        <aside
          hidden={hideBottomDock || undefined}
          className={`${hideBottomDock ? "hidden" : "flex"} flex-row shrink-0 border-t border-hairline bg-ice-1 dark:bg-charcoal-1 relative`}
          style={{ height: dockBottomHeight }}
          aria-label="Bottom dock"
        >
          {/* Resize grip — top edge */}
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize bottom dock"
            onPointerDown={onResizeDown}
            onPointerMove={onResizeMove}
            onPointerUp={onResizeUp}
            onPointerCancel={onResizeUp}
            className="absolute -top-[3px] left-0 right-0 h-[6px] cursor-ns-resize z-10"
          />
          {dockBottomIds.map((id) => (
            <div key={id} className="flex-1 min-w-0 border-r border-rule dark:border-charcoal-1 last:border-r-0 flex flex-col">
              <PanelLayoutPanel id={id} />
            </div>
          ))}
        </aside>
      )}
    </div>
  );

  // ── ONE stable tree for both presets and every fullscreen state ─────────
  // The route (mainSlot), the strip and every docked panel sit at the SAME
  // position in the element tree whichever preset is on and whichever pane
  // is fullscreen: the inset's pane shells are `display: contents` wrappers
  // in the docked preset, and fullscreen HIDES a pane (the `hidden`
  // attribute plus the `hidden` utility) instead of unmounting it. So a
  // preset toggle or a fullscreen round trip never remounts the route,
  // never loses a draft, and never drops a listener (F-17: "fullscreen that
  // keeps both panes mounted").
  //
  // C2, the Omarchy inset: an outer gap where the scene background shows,
  // and two tall rounded rectangles — the primary material (left dock +
  // main slot) on the left, the COMPANION (C4) or, in writing, the OUTLINE
  // (C5) on the right. From md up both panes are on screen (at md the
  // right narrows to RIGHT_PANE_MD_WIDTH and the left dock stays 0 px);
  // right-dock panels stack beneath the right pane.
  // NavRail is a sibling of this component in AppShell — the frame never
  // wraps it.
  const shownAlone: "left" | "right" | null = inset ? fullscreenPane : null;
  const leftHidden = shownAlone === "right";
  const rightHidden = shownAlone === "left";
  const rightFull = shownAlone === "right";
  const rightPaneWidth = tier === "md" ? RIGHT_PANE_MD_WIDTH : DOCK_WIDTH;
  const rightDockPanelIds = inset ? dockRightIds.filter((id) => !PANE_CONTENT_PANEL_IDS.has(id)) : dockRightIds;
  const leftDockWidth = inset
    ? dockLeftIds.length === 0 || tier === "md"
      ? 0
      : DOCK_WIDTH
    : dockSide("left", dockLeftIds.length);
  const rightDockWidth = dockSide("right", dockRightIds.length);
  const paneShell = (side: "left" | "right"): string =>
    "flex flex-col min-w-0 min-h-0 overflow-hidden border border-hairline " +
    "bg-ice-1 dark:bg-charcoal-1" +
    (focusedPane === side ? " ring-2 ring-inset ring-focus" : "");
  const leftDockHidden = inset && leftDockWidth === 0;
  const rightDockHidden = inset && rightDockPanelIds.length === 0;

  return (
    <div
      className={coreFlow.active ? "contents" : "relative h-full w-full flex bg-transparent overflow-hidden"}
      style={!coreFlow.active && inset ? { padding: INSET_GAP, gap: INSET_GAP } : undefined}
      data-layout-preset={inset ? "omarchy-inset" : undefined}
    >{/* SPR-04: root made transparent (was bg-ice-2 dark:bg-space-2) so the z-0 living mountainscape shows through the glassy route surface; the docks below keep their opaque chrome bg for legibility. */}
      {/* LEFT: the primary pane (inset) or a transparent wrapper (docked) */}
      <div
        {...(inset || coreFlow.active
          ? {
              "data-pane": "left",
              role: "region",
              "aria-label": "Primary pane",
              tabIndex: -1,
              style: coreFlow.style ?? { borderRadius: radius.lg },
              onFocusCapture: () => setFocusedPane("left"),
            }
          : {})}
        ref={coreFlow.ref}
        data-pane-host={coreFlow.hostKey}
        hidden={(coreFlow.active ? coreFlow.hidden : leftHidden) || undefined}
        className={coreFlow.active
          ? `${coreFlow.hidden ? "hidden" : "flex"} flex-col min-w-0 min-h-0 overflow-hidden border-2 rounded-none bg-ice-1 dark:bg-charcoal-1 ${coreFlow.focused ? "border-sun" : "border-hairline"}`
          : inset ? (leftHidden ? "hidden" : `flex-1 ${paneShell("left")}`) : "contents"}
      >
        <div className={inset || coreFlow.active ? "relative flex-1 min-h-0 w-full flex overflow-hidden" : "contents"}>
          {/* LEFT DOCK */}
          <aside
            hidden={leftDockHidden || undefined}
            className={
              leftDockHidden
                ? "hidden"
                : `flex flex-col shrink-0 min-w-0 ${dockTransition}` +
                  (inset ? "" : ` ${dockLeftIds.length ? "border-r border-hairline" : ""} bg-ice-1 dark:bg-charcoal-1`)
            }
            style={{ width: leftDockWidth }}
            aria-label="Left dock"
          >
            {dockLeftIds.filter((id) => !projectTreeOverlay || id !== "shortcuts:projecttree").map((id) => (
              <PanelLayoutPanel key={id} id={id} />
            ))}
          </aside>

          {/* CENTRE COLUMN: main + floating + bottom dock */}
          {centreColumn}
        </div>
      </div>

      {/* RIGHT: the companion pane (inset) or a transparent wrapper (docked) */}
      <div
        {...(inset || companionFlow.active
          ? {
              "data-pane": "right",
              role: "region",
              // Named for what it holds (B3-7): the outline in writing, the
              // agents in research and reading.
              "aria-label": writing ? "Outline pane" : "Agents pane",
              tabIndex: -1,
              // Right-pane fullscreen is fullscreen: the companion takes the
              // whole cockpit, never its column beside an empty scene.
              style: companionFlow.style ?? (rightFull
                ? { borderRadius: radius.lg }
                : { width: rightPaneWidth, borderRadius: radius.lg }),
              onFocusCapture: () => setFocusedPane("right"),
            }
          : {})}
        ref={companionFlow.ref}
        data-pane-host={companionFlow.hostKey}
        hidden={(companionFlow.active ? companionFlow.hidden : rightHidden) || undefined}
        className={
          companionFlow.active
            ? `${companionFlow.hidden ? "hidden" : "flex"} flex-col min-w-0 min-h-0 overflow-hidden border-2 rounded-none bg-ice-1 dark:bg-charcoal-1 ${companionFlow.focused ? "border-sun" : "border-hairline"}`
          : inset
            ? rightHidden
              ? "hidden"
              : `${rightFull ? "flex-1" : "shrink-0"} ${paneShell("right")}`
            : "contents"
        }
      >
        {inset ? <RightPaneForMode /> : null}
        {/* RIGHT DOCK */}
        <aside
          hidden={rightDockHidden || undefined}
          className={
            inset
              ? rightDockHidden
                ? "hidden"
                : "flex flex-col shrink-0 min-w-0 max-h-[50%] border-t border-hairline"
              : `flex flex-col shrink-0 ${dockRightIds.length ? "border-l border-hairline" : ""} bg-ice-1 dark:bg-charcoal-1 min-w-0 ${dockTransition}`
          }
          style={companionFlow.active && !inset ? { width: "100%", flex: 1, minHeight: 0 }
            : inset ? undefined : { width: rightDockWidth }}
          aria-label="Right dock"
        >
          {rightDockPanelIds.map((id) => (
            <PanelLayoutPanel key={id} id={id} />
          ))}
        </aside>
      </div>

      {projectTreeOverlay && <ProjectTreeOverlay />}

      {/* Fullscreen is never invisible state: a chip says it is on and is
          the pointer path back (Esc restores from any focus too). */}
      {fullscreenPane || paneZoom ? (
        <button
          type="button"
          data-fullscreen-chip
          onClick={() => paneZoom ? coreFlow.restoreZoom() : setFullscreenPane(null)}
          aria-label="Exit fullscreen (Esc)"
          title="Exit fullscreen (Esc)"
          className="absolute right-4 top-3 z-30 rounded-full border border-hairline bg-ice-0 dark:bg-charcoal-2 px-2.5 py-0.5 text-xxs text-ink-soft dark:text-moonlight shadow-z1 dark:shadow-z1-night hover:text-ink dark:hover:text-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
        >
          Fullscreen · Esc
        </button>
      ) : null}
    </div>
  );
}

export default PanelLayout;
