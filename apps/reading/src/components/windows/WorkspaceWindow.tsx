import { motion } from "framer-motion";
import { useCallback, useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { shadowForStackDepth } from "../../design/elevation";
import { emitWernerExperience } from "../../werner/reactionBus";
import { clampRectToViewport } from "../../workspace/panelLayoutLogic";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { WINDOW_Z_BASE, useWindows } from "../../workspace/windowsStore";
import type { AdFillView } from "../../modes/Reading/AdBorder";
import { WindowHostProvider } from "./windowHostContext";
import { WindowAdBorder } from "./WindowAdBorder";
import type { WindowAdEdge } from "./WindowAdBorder";

/**
 * WorkspaceWindow — a transparent, ad-bordered, draggable/expandable frame
 * that hosts a whole product page over the mountainscape (SPR-09 M1 + M7 + M8).
 *
 * Built ON the real floating primitives (not a reinvented window manager):
 *   - geometry + z-order + focus live in windowsStore (the SPR-09 slice),
 *   - drag/resize reuse the pointer-capture + clampRectToViewport pattern
 *     from PanelHandle / panelLayoutLogic,
 *   - reduced-motion + the glass tokens come straight from SPR-01.
 *
 * Body is glass (`bg-glass` + `backdrop-blur-glass`) so the scene shows
 * through; the page it hosts drops its own opaque bg via the window-adaptation
 * contract (useInWindow). Clicking anywhere in the window raises it.
 *
 * PERFORMANCE (M7): an unfocused window pauses its backdrop blur (the most
 * expensive transparent-surface cost) and dims slightly, so N windows + the
 * animated scene stay within budget — only the focused window pays for live
 * glass. A maximized ("full") window goes opaque, which lets the shell pause
 * the scene blur entirely behind it (documented degradation strategy).
 */

export interface WorkspaceWindowProps {
  id: string;
  /** The hosted product page. Rendered inside the glass body, under the
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
  const orderIndex = useWindows((s) => Math.max(0, s.order.indexOf(id)));
  const isFocused = useWindows((s) => s.focusedId === id);
  const focus = useWindows((s) => s.focus);
  const close = useWindows((s) => s.close);
  const setRect = useWindows((s) => s.setRect);
  const toggleMode = useWindows((s) => s.toggleMode);
  const reduceMotion = usePrefersReducedMotion();

  const rootRef = useRef<HTMLDivElement | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const resizeStart = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // M8 focus management — when a window mounts, remember what had focus and
  // move focus into the window; restore it on unmount (close).
  useEffect(() => {
    restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null;
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

  // M8 keyboard control — when the window (or its chrome) has focus, arrows
  // move it, ⌘/Ctrl+arrows resize it, Enter/F toggles full, Escape closes.
  // We only act when focus is on the window root or its title bar, so typing
  // inside the hosted page is never intercepted.
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!win) return;
      const active = document.activeElement;
      const onChrome =
        active === rootRef.current ||
        (active instanceof HTMLElement && active.closest("[data-window-titlebar]"));
      if (!onChrome) return;

      const STEP = 24;
      const mod = e.metaKey || e.ctrlKey;
      if (e.key === "Escape") {
        e.preventDefault();
        close(id);
        return;
      }
      if (e.key === "Enter" || e.key.toLowerCase() === "f") {
        e.preventDefault();
        toggleMode(id);
        return;
      }
      if (win.mode !== "floating") return;
      const arrow: Record<string, [number, number]> = {
        ArrowLeft: [-STEP, 0],
        ArrowRight: [STEP, 0],
        ArrowUp: [0, -STEP],
        ArrowDown: [0, STEP],
      };
      const delta = arrow[e.key];
      if (!delta) return;
      e.preventDefault();
      focus(id);
      if (mod) {
        setRect(id, {
          width: Math.max(MIN_W, win.rect.width + delta[0]),
          height: Math.max(MIN_H, win.rect.height + delta[1]),
        });
      } else {
        const viewport = {
          width: typeof window !== "undefined" ? window.innerWidth : 1440,
          height: typeof window !== "undefined" ? window.innerHeight : 900,
        };
        const clamped = clampRectToViewport(
          { ...win.rect, x: win.rect.x + delta[0], y: win.rect.y + delta[1] },
          viewport,
        );
        setRect(id, { x: clamped.x, y: clamped.y });
      }
    },
    [id, win, close, focus, setRect, toggleMode],
  );

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

  // PERF (M7): the focused floating window gets live glass blur; unfocused
  // windows drop the blur (cheapest big win) and dim slightly. A full window
  // goes opaque (bg-glass-solid) so the shell can pause the scene blur behind
  // it entirely — nothing of the scene is visible through a maximized window.
  const surfaceClass = isFull
    ? "bg-glass-solid"
    : isFocused
      ? "bg-glass backdrop-blur-glass"
      : "bg-glass opacity-95";

  let titleDepth = orderIndex;
  if (isFocused) {
    titleDepth = Math.min(3, titleDepth + 1);
  }
  const titleBarShadow = shadowForStackDepth(titleDepth, "glass-scene");

  return (
    <motion.div
      ref={rootRef}
      data-workspace-window={id}
      data-window-mode={win.mode}
      data-window-focused={isFocused ? "true" : "false"}
      role="dialog"
      aria-label={win.title}
      tabIndex={-1}
      initial={reduceMotion ? false : { scale: 0.97, opacity: 0 }}
      animate={{ scale: 1, opacity: isFull ? 1 : isFocused ? 1 : 0.95 }}
      exit={reduceMotion ? undefined : { scale: 0.97, opacity: 0 }}
      transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 320, damping: 30 }}
      style={geometry}
      className={
        surfaceClass +
        " border-edge border-glass rounded-hog flex flex-col overflow-hidden " +
        (isFocused
          ? " outline outline-2 outline-offset-[3px] outline-sun"
          : "")
      }
      onMouseDownCapture={() => focus(id)}
      onKeyDown={onKeyDown}
    >
      {/* TITLE BAR — drag handle + window actions */}
      <div
        data-window-titlebar
        tabIndex={0}
        aria-label={`${win.title} — window controls`}
        className={
          "shrink-0 flex items-center gap-2 px-2.5 py-1.5 select-none " +
          "border-b-edge border-glass bg-glass " +
          titleBarShadow +
          " " +
          (isFull ? "cursor-default" : "cursor-grab active:cursor-grabbing") +
          " focus:outline-none focus-visible:ring-2 focus-visible:ring-sun"
        }
        onPointerDown={onDragDown}
        onPointerMove={onDragMove}
        onPointerUp={onDragUp}
        onPointerCancel={onDragUp}
      >
        <span aria-hidden="true" className="font-mono text-shadow-1 dark:text-moonlight leading-none">
          ⋮⋮
        </span>
        <span className="flex-1 text-[12.5px] font-mono font-semibold truncate text-ink dark:text-bright">
          {win.title}
        </span>
        <button
          type="button"
          data-window-action="toggle"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => {
            emitWernerExperience("highlight");
            toggleMode(id);
          }}
          aria-label={isFull ? "Restore window to floating" : "Expand window to full"}
          className="px-1.5 leading-none text-[13px] text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
        >
          {isFull ? "❐" : "▢"}
        </button>
        <button
          type="button"
          data-window-action="close"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => {
            emitWernerExperience("note_saved");
            close(id);
          }}
          aria-label="Close window"
          className="px-1.5 leading-none text-[13px] text-shadow-1 dark:text-moonlight hover:text-emperor"
        >
          ✕
        </button>
      </div>

      {/* BODY — glass; hosts the product page. The page reads useInWindow()
          and drops its opaque bg + uses h-full (the window-adaptation
          contract). Padded by BORDER_INSET top/bottom so the ad rails never
          overlap the page. */}
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
