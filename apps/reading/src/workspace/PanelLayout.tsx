import { Suspense, lazy, useCallback, useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { toast } from "../components/lemon/LemonToast";
import { radius } from "../design/tokens";
import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { useWorkspace } from "./WorkspaceStore";
import { isTextEditing } from "./shortcuts";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";
import { useViewportTier } from "./useViewportTier";

// The companion pane (agent tabs, the thought-partner client) loads on first
// show, not with the entry chunk: most sessions open without it, and the
// entry chunk has a hard gzip budget (npm run build:check).
const CompanionPane = lazy(() => import("./CompanionPane"));

function CompanionPaneLoading() {
  return (
    <div role="status" aria-live="polite" className="flex-1 min-h-0 px-3 py-2 text-xs text-ink-mute dark:text-moonlight">
      Loading agents…
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
  const tier = useViewportTier();

  // S11 — at tier "lg" the two side docks can't both be visible; if both
  // have panels we collapse the right one (operator can flip via kebab).
  // At tier "md" docks disappear entirely — the panels would still render
  // but the dock widths drop to 0 so they collapse out of view.
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
  }, [tier, dockLeftIds.length, dockRightIds.length]);

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

  // Cockpit fullscreen restore (C3): Esc is scoped to the layout root — an
  // overlay's own key, the one sanctioned exception to the one-dispatcher
  // rule (never a global binding, never a keymap row). A key an element
  // claimed first (defaultPrevented) or pressed while typing stays theirs.
  const onLayoutKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!fullscreenPane || e.key !== "Escape" || e.defaultPrevented) return;
      if (isTextEditing(e.target as Element)) return;
      setFullscreenPane(null);
    },
    [fullscreenPane, setFullscreenPane],
  );

  // Tier `sm` (< 768px) is the phone layout: one column, the route view
  // alone and scrollable. The docks and floating panels stay out of it (a
  // 320px dock cannot fit), and there is no "use a larger screen" banner:
  // the shell around it (5-key dock, quiet header) is the phone design.
  if (tier === "sm") {
    return <div className="h-full w-full overflow-auto">{mainSlot}</div>;
  }

  // Fullscreen in the docked preset hides the bottom dock too (dockSide
  // already zeroes the side docks); the default state is untouched.
  const hideBottomDock = layoutPreset === "docked" && fullscreenPane !== null;

  // The centre column is IDENTICAL in both presets — one JSX value, so the
  // docked DOM is byte-identical to before the preset existed and the inset
  // preset cannot drift from it.
  const centreColumn = (
    <div className="flex-1 min-w-0 flex flex-col">
      <main className="flex-1 min-w-0 relative overflow-hidden">
        {/* Underlying mainSlot — the route content */}
        <div className="absolute inset-0 overflow-auto">{mainSlot}</div>

        {/* Floating layer — pointer-events:none container, panels opt back in */}
        <div className="absolute inset-0 pointer-events-none">
          {floatingIds.map((id) => (
            <div key={id} className="pointer-events-auto">
              <PanelLayoutPanel id={id} />
            </div>
          ))}
        </div>
      </main>

      {/* BOTTOM DOCK */}
      {dockBottomIds.length > 0 && !hideBottomDock && (
        <aside
          className="flex flex-row shrink-0 border-t border-hairline bg-ice-1 dark:bg-charcoal-1 relative"
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

  // ── C2: the Omarchy inset preset ────────────────────────────────────────
  // The SAME slot structure inside an inset frame: an outer gap where the
  // scene background shows, and two tall rounded rectangles — the primary
  // material (left dock + main slot) on the left, the COMPANION (C4) on the
  // right. Presentation only: dockSide()/collapse behavior, the {mainSlot}
  // contract and every consumer are unchanged. The right pane IS the
  // companion (D3): always present (its empty state offers "+ new agent");
  // any right-dock panels stack beneath it, collapsing as today. NavRail is
  // a sibling of this component in AppShell — the frame never wraps it.
  if (layoutPreset === "omarchy-inset") {
    const leftDockWidth = dockSide("left", dockLeftIds.length);
    // The companion pane measures as at least one content unit (it always
    // has content: the strip + the new-agent affordance), so the tier/lg
    // collapse rules in dockSide still govern its width.
    const rightPaneWidth = dockSide("right", Math.max(1, dockRightIds.length));
    const showLeftPane = fullscreenPane !== "right";
    const showRightPane = rightPaneWidth > 0 && fullscreenPane !== "left";
    const paneShell = (side: "left" | "right"): string =>
      "flex flex-col min-w-0 min-h-0 overflow-hidden border border-hairline " +
      "bg-ice-1 dark:bg-charcoal-1" +
      (focusedPane === side ? " ring-2 ring-inset ring-focus" : "");
    return (
      <div
        className="relative h-full w-full flex bg-transparent overflow-hidden"
        style={{ padding: INSET_GAP, gap: INSET_GAP }}
        data-layout-preset="omarchy-inset"
        onKeyDown={onLayoutKeyDown}
      >
        {showLeftPane && (
          <div
            data-pane="left"
            tabIndex={-1}
            aria-label="Primary pane"
            className={`flex-1 ${paneShell("left")}`}
            style={{ borderRadius: radius.lg }}
            onFocusCapture={() => setFocusedPane("left")}
          >
            <div className="relative h-full w-full flex overflow-hidden">
              {leftDockWidth > 0 && (
                <aside
                  className={`flex flex-col shrink-0 min-w-0 ${dockTransition}`}
                  style={{ width: leftDockWidth }}
                  aria-label="Left dock"
                >
                  {dockLeftIds.map((id) => (
                    <PanelLayoutPanel key={id} id={id} />
                  ))}
                </aside>
              )}
              {centreColumn}
            </div>
          </div>
        )}
        {showRightPane && (
          <div
            data-pane="right"
            tabIndex={-1}
            aria-label="Companion pane"
            className={`shrink-0 ${paneShell("right")}`}
            style={{ width: rightPaneWidth, borderRadius: radius.lg }}
            onFocusCapture={() => setFocusedPane("right")}
          >
            <Suspense fallback={<CompanionPaneLoading />}>
              <CompanionPane />
            </Suspense>
            {dockRightIds.length > 0 && (
              <aside
                className="flex flex-col shrink-0 min-w-0 max-h-[50%] border-t border-hairline"
                aria-label="Right dock"
              >
                {dockRightIds.map((id) => (
                  <PanelLayoutPanel key={id} id={id} />
                ))}
              </aside>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="relative h-full w-full flex bg-transparent overflow-hidden" onKeyDown={onLayoutKeyDown}>{/* SPR-04: root made transparent (was bg-ice-2 dark:bg-space-2) so the z-0 living mountainscape shows through the glassy route surface; the docks below keep their opaque chrome bg for legibility. */}
      {/* LEFT DOCK */}
      <aside
        className={`flex flex-col shrink-0 ${dockLeftIds.length ? "border-r border-hairline" : ""} bg-ice-1 dark:bg-charcoal-1 min-w-0 ${dockTransition}`}
        style={{ width: dockSide("left", dockLeftIds.length) }}
        aria-label="Left dock"
      >
        {dockLeftIds.map((id) => (
          <PanelLayoutPanel key={id} id={id} />
        ))}
      </aside>

      {/* CENTRE COLUMN: main + floating + bottom dock */}
      {centreColumn}

      {/* RIGHT DOCK */}
      <aside
        className={`flex flex-col shrink-0 ${dockRightIds.length ? "border-l border-hairline" : ""} bg-ice-1 dark:bg-charcoal-1 min-w-0 ${dockTransition}`}
        style={{ width: dockSide("right", dockRightIds.length) }}
        aria-label="Right dock"
      >
        {dockRightIds.map((id) => (
          <PanelLayoutPanel key={id} id={id} />
        ))}
      </aside>
    </div>
  );
}

export default PanelLayout;
