import type { ReactNode } from "react";

import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { useWorkspace } from "./WorkspaceStore";

/**
 * PanelLayout — the orchestrator.
 *
 * Lays out three vertical zones:
 *   ┌──────────┬───────────────────────────┬──────────┐
 *   │          │                           │          │
 *   │  LEFT    │       MAIN SLOT           │  RIGHT   │
 *   │  DOCK    │   (caller-supplied; the   │  DOCK    │
 *   │          │    route Outlet, usually) │          │
 *   │          │   + FLOATING LAYER over   │          │
 *   │          │     the main slot         │          │
 *   └──────────┴───────────────────────────┴──────────┘
 *
 * Each dock column animates its width to 0 when empty so the main slot
 * gets the full viewport when there are no docked panels.
 *
 * S5 introduces a fourth zone (bottom dock) for the Chat surface.
 * The S3 ship only does left + right + floating + popout-stubbed.
 */
type Props = { mainSlot: ReactNode };

const DOCK_WIDTH = 320;

export function PanelLayout({ mainSlot }: Props) {
  const dockLeftIds = useWorkspace((s) => s.dockLeftIds);
  const dockRightIds = useWorkspace((s) => s.dockRightIds);
  const floatingIds = useWorkspace((s) => s.floatingIds);

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

      {/* MAIN */}
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
