import { motion } from "framer-motion";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { MutableRefObject, ReactNode, RefObject } from "react";

import { opaquePanelShadowClasses } from "../design/elevation";
import { surfaceSpring } from "../design/motion";

import { escOverlayOpen, ESC_OVERLAY_PROPS } from "./escapeOverlay";
import { PanelHandle } from "./PanelHandle";
import { PanelRegistry } from "./PanelRegistry";
import { useWorkspace } from "./WorkspaceStore";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";
import type { PanelDescriptor } from "./panel.types";

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
type Props = { id: string; content?: ReactNode; bare?: boolean };

export function PanelLayoutPanel({ id, content, bare = false }: Props) {
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
  //
  // One Esc reaches exactly one handler (lane A B2-2, R2-M2): a key another
  // handler already claimed (defaultPrevented) is not this panel's, nor is
  // an Esc while the panel sits in a pane fullscreen has hidden (kept
  // mounted, off screen). While focused and on screen the panel is an Esc
  // overlay (ESC_OVERLAY_PROPS below), so the fullscreen restore defers to
  // it and the NEXT Esc restores the panes.
  useEffect(() => {
    if (!panel || panel.mode !== "floating" || !isFocused) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (rootRef.current?.closest("[hidden]")) return;
      if (escOverlayOpen(document, rootRef.current)) return;
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
  usePanelFocusTrap(rootRef, panel);

  if (!panel && content === undefined) return null;
  const Renderer = panel ? PanelRegistry[panel.kind] : null;
  const body = content === undefined ? (Renderer && panel ? <Renderer {...panel.props} /> : null) : content;

  // popout — rendering is owned by the popout window (S9).
  if (!bare && panel?.mode === "popout") return null;

  // floating
  if (!bare && panel?.mode === "floating") {
    return <FloatingPanelFrame panel={panel} isFocused={isFocused} reduceMotion={reduceMotion}
      rootRef={rootRef} onMouseDown={onMouseDownRaise}>{body}</FloatingPanelFrame>;
  }

  return <DockedPanelFrame panel={panel} bare={bare} isFocused={isFocused} rootRef={rootRef}>{body}</DockedPanelFrame>;
}

function FloatingPanelFrame({ panel, isFocused, reduceMotion, rootRef, onMouseDown, children }: {
  panel: PanelDescriptor;
  isFocused: boolean;
  reduceMotion: boolean;
  rootRef: MutableRefObject<HTMLElement | null>;
  onMouseDown: () => void;
  children: ReactNode;
}) {
  const shadow = opaquePanelShadowClasses(panel.zIndex, isFocused);
  return (
    <motion.div layout={false}
      initial={reduceMotion ? false : { scale: 0.96, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={reduceMotion ? undefined : { scale: 0.96, opacity: 0 }}
      transition={reduceMotion ? { duration: 0 } : surfaceSpring}
      style={{ position: "absolute", top: panel.rect.y, left: panel.rect.x,
        width: panel.rect.width, height: panel.rect.height, zIndex: panel.zIndex }}
      className={"bg-ice-0 dark:bg-charcoal-2 border border-rule rounded-hog flex flex-col overflow-hidden " +
        shadow + (isFocused ? " outline outline-2 outline-offset-[3px] outline-sun" : " opacity-95")}
      onMouseDownCapture={onMouseDown} role="region" aria-label={panel.title}
      {...(isFocused ? ESC_OVERLAY_PROPS : {})}
      ref={(element) => { rootRef.current = element; }}>
      <PanelHandle id={panel.id} draggable resizable />
      <div className="flex-1 min-h-0 overflow-auto">
        <Suspense fallback={<PanelLoading />}>{children}</Suspense>
      </div>
    </motion.div>
  );
}

function DockedPanelFrame({ panel, bare, isFocused, rootRef, children }: {
  panel: PanelDescriptor | undefined;
  bare: boolean;
  isFocused: boolean;
  rootRef: MutableRefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  return (
    <div
      className={
        "flex flex-col " +
        (bare ? "flex-1 min-h-0 " : "bg-ice-0 dark:bg-charcoal-2 " + (panel?.mode === "docked-bottom"
          ? "h-full"
          : "border-b border-rule dark:border-charcoal-1 min-h-[140px] flex-1 ")) +
        "overflow-hidden " +
        (bare || isFocused ? "" : "opacity-95")
      }
      onMouseDownCapture={panel ? () => useWorkspace.getState().focus(panel.id) : undefined}
      role={bare ? undefined : "region"}
      aria-label={bare ? undefined : panel?.title}
      ref={(el) => {
        rootRef.current = el;
      }}
    >
      {!bare && panel ? <PanelHandle id={panel.id} draggable={false} resizable={false} /> : null}
      <div className="flex-1 min-h-0 overflow-auto">
        <Suspense fallback={<PanelLoading />}>
          {children}
        </Suspense>
      </div>
    </div>
  );
}

function usePanelFocusTrap(rootRef: MutableRefObject<HTMLElement | null>, panel: PanelDescriptor | undefined) {
  useEffect(() => {
    if (!panel) return;
    const root = rootRef.current;
    if (!root) return;
    const focusable =
      'a[href], button:not([disabled]), textarea:not([disabled]), ' +
      'input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !root.contains(document.activeElement)) return;
      const nodes = Array.from(root.querySelectorAll<HTMLElement>(focusable))
        .filter((element) => !element.hasAttribute("disabled"));
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    root.addEventListener("keydown", onKey);
    return () => root.removeEventListener("keydown", onKey);
  }, [panel, rootRef]);
}

function PanelLoading() {
  return (
    <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">
      Loading…
    </div>
  );
}

export default PanelLayoutPanel;
