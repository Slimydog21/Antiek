import { motion } from "framer-motion";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { opaquePanelShadowClasses } from "../design/elevation";

import { PanelHandle } from "./PanelHandle";
import { PanelRegistry } from "./PanelRegistry";
import { PanelInstanceProvider } from "./panelInstanceContext";
import { useWorkspace } from "./WorkspaceStore";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

/**
 * Hook: subscribe to a panel's actual rendered size, debounced so it
 * only emits after the operator stops resizing for `debounceMs`.
 *
 * Used by heavy-embed children (pdf.js, canvas-renderers) that thrash
 * if they re-rasterise on every animation frame of a resize gesture.
 * During the gesture they keep their previous render; a single
 * re-render fires once size settles.
 *
 *   const [ref, size] = usePanelSizeStable();
 *   // attach `ref` to a stable outer container; rerender on `size`.
 */
export function usePanelSizeStable<T extends HTMLElement = HTMLDivElement>(
  debounceMs = 120,
): [RefObject<T | null>, { w: number; h: number } | null] {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setSize({ w: r.width, h: r.height }), debounceMs);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (timer) clearTimeout(timer);
    };
  }, [debounceMs]);
  return [ref, size];
}

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
  const reduceMotion = usePrefersReducedMotion();

  const onMouseDownRaise = useCallback(() => {
    if (panel && panel.mode === "floating") bringToFront(id);
  }, [panel, id, bringToFront]);

  // S3 acceptance: ESC closes the focused floating panel.
  // Only listens when this panel is the focused-floating one. Ignores
  // ESC while focus is inside an editable element so the operator can
  // still use Escape to cancel inline edits.
  useEffect(() => {
    if (!panel || panel.mode !== "floating" || !isFocused) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const t = e.target as HTMLElement | null;
      if (t) {
        const tag = t.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;
        if (t.isContentEditable) return;
      }
      e.preventDefault();
      useWorkspace.getState().close(id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, isFocused, id]);

  // S11 acceptance: in-panel focus trap. Tab inside a panel cycles
  // between the panel's focusable descendants; reaching the last and
  // pressing Tab wraps back to the first (and vice versa for Shift+
  // Tab on the first). The operator switches panels via ⌘[ / ⌘].
  const rootRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!panel) return;
    const root = rootRef.current;
    if (!root) return;
    const FOCUSABLE =
      'a[href], button:not([disabled]), textarea:not([disabled]), ' +
      'input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      if (!root.contains(document.activeElement)) return;
      const nodes = Array.from(
        root.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => !el.hasAttribute("disabled"));
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    root.addEventListener("keydown", onKey);
    return () => root.removeEventListener("keydown", onKey);
  }, [panel]);

  if (!panel) return null;
  const Renderer = PanelRegistry[panel.kind];

  // popout — rendering is owned by the popout window (S9).
  if (panel.mode === "popout") return null;

  // floating
  if (panel.mode === "floating") {
    const shadow = opaquePanelShadowClasses(panel.zIndex, isFocused);
    return (
      <motion.div
        layout={false}
        initial={reduceMotion ? false : { scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={reduceMotion ? undefined : { scale: 0.96, opacity: 0 }}
        transition={
          reduceMotion
            ? { duration: 0 }
            : { type: "spring", stiffness: 320, damping: 28 }
        }
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
          shadow +
          (isFocused
            ? " outline outline-2 outline-offset-[3px] outline-sun"
            : " opacity-95")
        }
        onMouseDownCapture={onMouseDownRaise}
        role="region"
        aria-label={panel.title}
        ref={(el) => {
          rootRef.current = el;
        }}
      >
        <PanelHandle id={id} draggable resizable />
        <div className="flex-1 min-h-0 overflow-auto">
          <Suspense fallback={<PanelLoading />}>
            <PanelInstanceProvider value={id}>
              <Renderer {...panel.props} />
            </PanelInstanceProvider>
          </Suspense>
        </div>
      </motion.div>
    );
  }

  // docked-left / docked-right / docked-bottom — flat, sit in the dock column
  return (
    <div
      className={
        "flex flex-col bg-ice-0 dark:bg-charcoal-2 " +
        (panel.mode === "docked-bottom"
          ? "h-full"
          : "border-b border-rule dark:border-charcoal-1 min-h-[140px] flex-1 ") +
        "overflow-hidden " +
        (isFocused ? "" : "opacity-95")
      }
      onMouseDownCapture={() => useWorkspace.getState().focus(id)}
      role="region"
      aria-label={panel.title}
      ref={(el) => {
        rootRef.current = el;
      }}
    >
      <PanelHandle id={id} draggable={false} resizable={false} />
      <div className="flex-1 min-h-0 overflow-auto">
        <Suspense fallback={<PanelLoading />}>
          <PanelInstanceProvider value={id}>
            <Renderer {...panel.props} />
          </PanelInstanceProvider>
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
