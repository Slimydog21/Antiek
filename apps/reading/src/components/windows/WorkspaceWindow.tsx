import { motion } from "framer-motion";
import { useCallback, useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

import { surfaceSpring } from "../../design/motion";
import { escOverlayOpen } from "../../workspace/escapeOverlay";
import { clampRectToViewport } from "../../workspace/panelLayoutLogic";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { WINDOW_Z_BASE, useWindows } from "../../workspace/windowsStore";
import type { AdFillView } from "../../modes/Reading/AdBorder";
import { WindowHostProvider } from "./windowHostContext";
import { WindowAdBorder } from "./WindowAdBorder";
import type { WindowAdEdge } from "./WindowAdBorder";
import { WINDOW_KEYBOARD_HELP, WINDOW_KEYBOARD_SHORTCUTS, windowCommand } from "./windowKeyboard";

/** A product window with stable store identity, local frame keys and parent-supplied ads. */

export interface WorkspaceWindowProps {
  id: string;
  /** The hosted product page. Rendered inside the opaque body, under the
   *  WindowHostProvider so it adapts per the contract. */
  children: ReactNode;
  /** Parent-supplied ad fills for the Times-Square border (never fetched). */
  adFills?: Partial<Record<WindowAdEdge, AdFillView>>;
  adSuppressed?: Partial<Record<WindowAdEdge, boolean>>;
  onAdImpression?: (slotId: string, advertiserName: string) => void;
  onAdSuppressed?: (slotId: string, reason: string) => void;
  onOpenHouse?: (documentId: string) => void;
}

const MIN_W = 360;
const MIN_H = 240;
/** The band reserved inside the window for the ad border, so the hosted page
 *  never sits under a rail. Mirrors the reading AdBorder min-height (44px). */
const BORDER_INSET = 46;

export function WorkspaceWindow({
  id,
  children,
  adFills,
  adSuppressed,
  onAdImpression,
  onAdSuppressed,
  onOpenHouse,
}: WorkspaceWindowProps) {
  const win = useWindows((s) => s.windows[id]);
  const isFocused = useWindows((s) => s.focusedId === id);
  const focus = useWindows((s) => s.focus);
  const close = useWindows((s) => s.close);
  const setRect = useWindows((s) => s.setRect);
  const toggleMode = useWindows((s) => s.toggleMode);
  const reduceMotion = usePrefersReducedMotion();

  const rootRef = useRef<HTMLDivElement | null>(null);
  const titleRef = useRef<HTMLDivElement | null>(null);
  const keyboardHelpId = useId();
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const resizeStart = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // M8 focus management — when a window mounts, remember what had focus and
  // move focus into the window; restore it on unmount (close).
  useEffect(() => {
    const active = document.activeElement;
    restoreFocusRef.current = active instanceof HTMLElement ? active : null;
    // Defer so the element exists + framer-motion's initial frame has run.
    const t = window.setTimeout(() => rootRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(t);
      const prev = restoreFocusRef.current;
      if (prev && typeof prev.focus === "function" && document.contains(prev)) {
        prev.focus();
      }
    };
  }, []);

  // Re-opening a stable-id window does not remount it. When store focus moves
  // back here, move DOM focus too so keyboard and assistive-tech users receive
  // the same context transition as on the initial open.
  useEffect(() => {
    const root = rootRef.current;
    if (isFocused && root && !root.contains(document.activeElement)) {
      root.focus();
    }
  }, [isFocused, win?.z]);

  const onDragDown = useCallback(
    (e: React.PointerEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("[data-window-action]")) return;
      (e.currentTarget as Element).setPointerCapture(e.pointerId);
      dragStart.current = { x: e.clientX, y: e.clientY };
      focus(id);
    },
    [id, focus],
  );

  const onDragMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragStart.current || !win || win.mode !== "floating") return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      dragStart.current = { x: e.clientX, y: e.clientY };
      const viewport = {
        width: typeof window !== "undefined" ? window.innerWidth : 1440,
        height: typeof window !== "undefined" ? window.innerHeight : 900,
      };
      // Reuse the panel clamp so a window can never be dragged fully off-screen.
      const clamped = clampRectToViewport(
        { ...win.rect, x: win.rect.x + dx, y: win.rect.y + dy },
        viewport,
      );
      setRect(id, { x: clamped.x, y: clamped.y });
    },
    [id, win, setRect],
  );

  const onDragUp = useCallback(() => {
    dragStart.current = null;
  }, []);

  const onResizeDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as Element).setPointerCapture(e.pointerId);
      if (!win) return;
      resizeStart.current = {
        x: e.clientX,
        y: e.clientY,
        w: win.rect.width,
        h: win.rect.height,
      };
      focus(id);
    },
    [id, win, focus],
  );

  const onResizeMove = useCallback(
    (e: React.PointerEvent) => {
      if (!resizeStart.current) return;
      const dx = e.clientX - resizeStart.current.x;
      const dy = e.clientY - resizeStart.current.y;
      setRect(id, {
        width: Math.max(MIN_W, resizeStart.current.w + dx),
        height: Math.max(MIN_H, resizeStart.current.h + dy),
      });
    },
    [id, setRect],
  );

  const onResizeUp = useCallback(() => {
    resizeStart.current = null;
  }, []);

  const onFocusCapture = useCallback((event: React.FocusEvent) => {
    if (!(event.target instanceof Element) ||
        event.target.closest("[data-workspace-window]") !== rootRef.current) return;
    const current = useWindows.getState();
    if (current.focusedId !== id) current.focus(id);
  }, [id]);

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    const target = event.target;
    if (target !== document.activeElement ||
        (target !== rootRef.current && target !== titleRef.current) || escOverlayOpen()) return;
    const command = windowCommand(event.nativeEvent);
    if (!command) return;
    const current = useWindows.getState();
    const currentWindow = current.windows[id];
    if (!currentWindow) return;
    if ((command.kind === "move" || command.kind === "resize") && currentWindow.mode !== "floating") return;
    event.preventDefault();
    if (command.kind === "close") {
      current.close(id);
      return;
    }
    if (command.kind === "toggle") {
      current.toggleMode(id);
      return;
    }
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const rect = currentWindow.rect;
    if (command.kind === "resize") {
      const maxWidth = Math.max(MIN_W, viewport.width - Math.max(0, rect.x));
      const maxHeight = Math.max(MIN_H, viewport.height - Math.max(0, rect.y));
      current.setRect(id, {
        width: Math.min(maxWidth, Math.max(MIN_W, rect.width + command.dx)),
        height: Math.min(maxHeight, Math.max(MIN_H, rect.height + command.dy)),
      });
    } else {
      const clamped = clampRectToViewport(
        { ...rect, x: rect.x + command.dx, y: rect.y + command.dy }, viewport,
      );
      current.setRect(id, { x: clamped.x, y: clamped.y });
    }
  }, [id]);

  if (!win) return null;

  const isFull = win.mode === "full";

  // Geometry. Full = fill the working region (inset-0); floating = the rect.
  const geometry: React.CSSProperties = isFull
    ? { position: "absolute", inset: 0, zIndex: WINDOW_Z_BASE + win.z }
    : {
        position: "absolute",
        top: win.rect.y,
        left: win.rect.x,
        width: win.rect.width,
        height: win.rect.height,
        zIndex: WINDOW_Z_BASE + win.z,
      };

  return (
    <motion.div
      ref={rootRef}
      data-workspace-window={id}
      data-window-mode={win.mode}
      data-window-focused={isFocused ? "true" : "false"}
      role="dialog"
      aria-label={win.title}
      aria-describedby={keyboardHelpId}
      aria-keyshortcuts={WINDOW_KEYBOARD_SHORTCUTS}
      tabIndex={-1}
      initial={reduceMotion ? false : { scale: 0.97, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={reduceMotion ? undefined : { scale: 0.97, opacity: 0 }}
      transition={reduceMotion ? { duration: 0 } : surfaceSpring}
      style={geometry}
      className={
        "bg-glass-solid border-2 rounded-none flex flex-col overflow-hidden " +
        (isFocused ? "border-sun" : "border-glass")
      }
      onFocusCapture={onFocusCapture}
      onMouseDownCapture={() => focus(id)}
      onKeyDown={onKeyDown}
    >
      {/* TITLE BAR — drag handle + window actions */}
      <div
        ref={titleRef}
        data-window-titlebar
        tabIndex={0}
        aria-label={`${win.title} — window controls`}
        aria-describedby={keyboardHelpId}
        aria-keyshortcuts={WINDOW_KEYBOARD_SHORTCUTS}
        className={
          "h-[26px] shrink-0 flex items-center gap-2 px-2 select-none text-xs " +
          "border-b border-glass bg-glass-solid " +
          (isFull ? "cursor-default" : "cursor-grab active:cursor-grabbing") +
          " focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-sun"
        }
        onPointerDown={onDragDown}
        onPointerMove={onDragMove}
        onPointerUp={onDragUp}
        onPointerCancel={onDragUp}
      >
        <span aria-hidden="true" className="font-mono text-shadow-1 dark:text-moonlight leading-none">
          ⋮⋮
        </span>
        <span className="flex-1 text-xs font-mono font-semibold truncate text-ink dark:text-bright">
          {win.title}
        </span>
        <button
          type="button"
          data-window-action="toggle"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => toggleMode(id)}
          aria-label={isFull ? "Restore window to floating" : "Expand window to full"}
          className="px-1.5 leading-none text-xs text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
        >
          {isFull ? "❐" : "▢"}
        </button>
        <button
          type="button"
          data-window-action="close"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => close(id)}
          aria-label="Close window"
          className="px-1.5 leading-none text-xs text-shadow-1 dark:text-moonlight hover:text-emperor"
        >
          ✕
        </button>
      </div>

      <p id={keyboardHelpId} className="shrink-0 m-0 px-2 py-1 font-mono text-xs leading-4 text-shadow-1 dark:text-moonlight">
        {WINDOW_KEYBOARD_HELP}
      </p>

      {/* Ad insets keep the mounted product clear of the border rails. */}
      <div
        className="relative flex-1 min-h-0"
        style={{ paddingTop: BORDER_INSET, paddingBottom: BORDER_INSET }}
      >
        <div className="absolute inset-0 overflow-auto" style={{ top: BORDER_INSET, bottom: BORDER_INSET }}>
          <WindowHostProvider value={true}>{children}</WindowHostProvider>
        </div>

        {/* TIMES-SQUARE AD BORDER — parent fills, house fallback, suppression. */}
        <WindowAdBorder
          windowId={id}
          fills={adFills}
          suppressed={adSuppressed}
          onImpression={onAdImpression}
          onSuppressed={onAdSuppressed}
          onOpenHouse={onOpenHouse}
        />
      </div>

      {/* RESIZE GRIP — floating only (bottom-right). */}
      {!isFull && (
        <div
          title="Resize window"
          data-window-action="resize"
          onPointerDown={onResizeDown}
          onPointerMove={onResizeMove}
          onPointerUp={onResizeUp}
          onPointerCancel={onResizeUp}
          className="absolute right-0 bottom-0 w-4 h-4 cursor-nwse-resize z-20 border-r-edge border-b-edge border-sun"
        />
      )}
    </motion.div>
  );
}

export default WorkspaceWindow;
