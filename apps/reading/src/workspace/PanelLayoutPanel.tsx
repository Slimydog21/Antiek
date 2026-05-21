import { motion } from "framer-motion";
import { Suspense, useCallback } from "react";

import { PanelHandle } from "./PanelHandle";
import { PanelRegistry } from "./PanelRegistry";
import { useWorkspace } from "./WorkspaceStore";

/**
 * PanelLayoutPanel — renders one panel descriptor.
 *
 * Three concrete branches based on `panel.mode`:
 *
 *   docked-left / docked-right
 *     Flat chrome — no shadow, no border-radius (the dock is the frame).
 *     The PanelHandle still gives the operator drag-aside / float / close.
 *
 *   floating
 *     Absolutely-positioned card with sun-yellow border + offset shadow.
 *     Focused: shadow-z3. Unfocused: shadow-z2 + slight opacity drop.
 *     Resizable from the bottom-right; draggable from the handle.
 *     Animated in/out via framer-motion (spring).
 *
 *   popout
 *     S9 implements the actual window.open + cross-window sync.
 *     S3 stubs this — the panel just doesn't render in-tab.
 */
type Props = { id: string };

export function PanelLayoutPanel({ id }: Props) {
  const panel = useWorkspace((s) => s.panels[id]);
  const isFocused = useWorkspace((s) => s.focusedPanelId === id);
  const bringToFront = useWorkspace((s) => s.bringToFront);

  const onMouseDownRaise = useCallback(() => {
    if (panel && panel.mode === "floating") bringToFront(id);
  }, [panel, id, bringToFront]);

  if (!panel) return null;
  const Renderer = PanelRegistry[panel.kind];

  // popout — S3 stub: rendering is owned by the popout window (S9).
  if (panel.mode === "popout") return null;

  // floating
  if (panel.mode === "floating") {
    return (
      <motion.div
        layout={false}
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: "spring", stiffness: 320, damping: 28 }}
        style={{
          position: "absolute",
          top: panel.rect.y,
          left: panel.rect.x,
          width: panel.rect.width,
          height: panel.rect.height,
          zIndex: panel.zIndex,
        }}
        className={
          "bg-ice-0 dark:bg-charcoal-2 " +
          "border-edge border-sun rounded-hog " +
          "flex flex-col overflow-hidden " +
          (isFocused
            ? "shadow-z3 dark:shadow-z3-night"
            : "shadow-z2 dark:shadow-z2-night opacity-95")
        }
        onMouseDownCapture={onMouseDownRaise}
        role="region"
        aria-label={panel.title}
      >
        <PanelHandle id={id} draggable resizable />
        <div className="flex-1 min-h-0 overflow-auto">
          <Suspense fallback={<PanelLoading />}>
            <Renderer {...panel.props} />
          </Suspense>
        </div>
      </motion.div>
    );
  }

  // docked-left / docked-right — flat, sit in the dock column
  return (
    <div
      className={
        "flex flex-col bg-ice-0 dark:bg-charcoal-2 " +
        "border-b border-rule dark:border-charcoal-1 " +
        "min-h-[140px] flex-1 overflow-hidden " +
        (isFocused ? "" : "opacity-95")
      }
      onMouseDownCapture={() => useWorkspace.getState().focus(id)}
      role="region"
      aria-label={panel.title}
    >
      <PanelHandle id={id} draggable={false} resizable={false} />
      <div className="flex-1 min-h-0 overflow-auto">
        <Suspense fallback={<PanelLoading />}>
          <Renderer {...panel.props} />
        </Suspense>
      </div>
    </div>
  );
}

function PanelLoading() {
  return (
    <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">
      Loading…
    </div>
  );
}

export default PanelLayoutPanel;
