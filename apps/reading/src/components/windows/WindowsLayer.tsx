import { AnimatePresence } from "framer-motion";
import { Suspense } from "react";

import { useWindows } from "../../workspace/windowsStore";
import { WINDOW_PAGES } from "./openWindow";
import { WorkspaceWindow } from "./WorkspaceWindow";

/**
 * WindowsLayer — renders every open workspace window over the scene (SPR-09).
 *
 * Mount this ONCE inside the shell's working region, as a sibling overlaying
 * the route Outlet (it is `absolute inset-0 pointer-events-none`; each window
 * re-enables pointer events on itself). Because AppShell is owned by SPR-04,
 * this layer is self-contained: dropping
 *
 *     <WindowsLayer />
 *
 * into the working region's relative container is the entire integration — it
 * reads windowsStore + the WINDOW_PAGES registry and needs no props. The
 * orchestrator/SPR-04 owner wires that one line; SPR-09 keeps AppShell.tsx
 * untouched (hard constraint).
 *
 * Render order follows `order` (last = topmost). The inert empty layer stays
 * mounted as the authoritative coordinate origin for anchor-aware opens;
 * pointer-events remain disabled until a child window enables them.
 * AnimatePresence gives the close/open spring (disabled under reduced-motion
 * inside WorkspaceWindow).
 */
export function WindowsLayer() {
  const order = useWindows((s) => s.order);
  const windows = useWindows((s) => s.windows);

  return (
    <div data-windows-layer className="absolute inset-0 pointer-events-none z-30">
      <AnimatePresence>
        {order.map((id) => {
          const win = windows[id];
          if (!win) return null;
          const page = WINDOW_PAGES[win.kind];
          const Renderer = page?.renderer;
          return (
            <div key={id} className="pointer-events-auto">
              <WorkspaceWindow id={id}>
                {Renderer ? (
                  <Suspense
                    fallback={
                      <div className="p-6 text-sm text-shadow-1 dark:text-moonlight italic">
                        Loading…
                      </div>
                    }
                  >
                    <Renderer {...win.payload} />
                  </Suspense>
                ) : (
                  <div className="p-6 text-sm text-emperor">
                    No renderer registered for window kind “{win.kind}”.
                  </div>
                )}
              </WorkspaceWindow>
            </div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

export default WindowsLayer;
