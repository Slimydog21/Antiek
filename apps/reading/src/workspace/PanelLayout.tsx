import { useCallback, useRef } from "react";
import type { ReactNode } from "react";

import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { useWorkspace } from "./WorkspaceStore";

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

export function PanelLayout({ mainSlot }: Props) {
  const dockLeftIds = useWorkspace((s) => s.dockLeftIds);
  const dockRightIds = useWorkspace((s) => s.dockRightIds);
  const dockBottomIds = useWorkspace((s) => s.dockBottomIds);
  const floatingIds = useWorkspace((s) => s.floatingIds);
  const dockBottomHeight = useWorkspace((s) => s.dockBottomHeight);
  const setDockBottomHeight = useWorkspace((s) => s.setDockBottomHeight);

  // Pointer-event-based vertical resize of the bottom dock.
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

  return (
    <div className="relative h-full w-full flex bg-ice-2 dark:bg-space-2 overflow-hidden">
      {/* LEFT DOCK */}
      <aside
        className="flex flex-col shrink-0 border-r-edge border-sun bg-ice-1 dark:bg-charcoal-1 min-w-0 transition-[width] duration-150 ease-out"
        style={{ width: dockLeftIds.length ? DOCK_WIDTH : 0 }}
        aria-label="Left dock"
      >
        {dockLeftIds.map((id) => (
          <PanelLayoutPanel key={id} id={id} />
        ))}
      </aside>

      {/* CENTRE COLUMN: main + floating + bottom dock */}
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
        {dockBottomIds.length > 0 && (
          <aside
            className="flex flex-row shrink-0 border-t-edge border-sun bg-ice-1 dark:bg-charcoal-1 relative"
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

      {/* RIGHT DOCK */}
      <aside
        className="flex flex-col shrink-0 border-l-edge border-sun bg-ice-1 dark:bg-charcoal-1 min-w-0 transition-[width] duration-150 ease-out"
        style={{ width: dockRightIds.length ? DOCK_WIDTH : 0 }}
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
