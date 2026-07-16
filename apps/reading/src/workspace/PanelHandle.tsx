import { useCallback, useRef } from "react";

import LemonButton from "../components/lemon/LemonButton";
import { LemonDropdown, LemonMenuItem } from "../components/lemon/LemonDropdown";
import { press } from "../design/motion";

import { useWorkspace } from "./WorkspaceStore";
import { clampRectToViewport } from "./panelLayoutLogic";
import { openPopoutFor } from "./popout";
import type { PanelMode } from "./panel.types";
import { emitWernerExperience } from "../werner/reactionBus";

/**
 * PanelHandle — the title strip rendered at the top of every panel.
 *
 * Layout:
 *   ┌──── ☰ Title ─────────────────────── 📌  ⋯  ✕ ────┐
 *
 *   ☰   drag grip (only meaningful in `floating` mode)
 *   📌  pin / unpin (operator-toggleable)
 *   ⋯   kebab → LemonDropdown of mode actions
 *   ✕   close
 *
 * Drag is hand-rolled with pointer-capture events. When the panel is
 * floating, dragging the grip writes the new `rect.x/y` through the
 * store's `setRect`. Resize handles are bottom-right (floating) only.
 */
type Props = {
  id: string;
  draggable: boolean;
  resizable?: boolean;
};

export function PanelHandle({ id, draggable, resizable = false }: Props) {
  const panel = useWorkspace((s) => s.panels[id]);
  const focused = useWorkspace((s) => s.focusedPanelId === id);
  const actions = useWorkspace.getState;
  const start = useRef<{ x: number; y: number } | null>(null);
  const resizeStart = useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (!draggable) return;
      // Stop the drag from firing on inputs / buttons inside the handle
      const target = e.target as HTMLElement;
      if (target.closest("[data-handle-action]")) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      start.current = { x: e.clientX, y: e.clientY };
      actions().bringToFront(id);
    },
    [draggable, id, actions],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!start.current) return;
      const dx = e.clientX - start.current.x;
      const dy = e.clientY - start.current.y;
      start.current = { x: e.clientX, y: e.clientY };
      const s = actions();
      const p = s.panels[id];
      if (!p) return;
      // Clamp the new position to the viewport so the panel can't be
      // dragged completely off-screen. `panelLayoutLogic.clampRectToViewport`
      // keeps at least 80px of the panel reachable on every side
      // (S3 acceptance criterion).
      const viewport = {
        width: typeof window !== "undefined" ? window.innerWidth : 1440,
        height: typeof window !== "undefined" ? window.innerHeight : 900,
      };
      const clamped = clampRectToViewport(
        { ...p.rect, x: p.rect.x + dx, y: p.rect.y + dy },
        viewport,
      );
      s.setRect(id, { x: clamped.x, y: clamped.y });
    },
    [id, actions],
  );

  const onPointerUp = useCallback(() => {
    start.current = null;
  }, []);

  // bottom-right resize handle (floating only). Hand-rolled, same idea.
  const onResizeDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as Element).setPointerCapture(e.pointerId);
      const p = actions().panels[id];
      if (!p) return;
      resizeStart.current = {
        x: e.clientX,
        y: e.clientY,
        w: p.rect.width,
        h: p.rect.height,
      };
    },
    [id, actions],
  );
  const onResizeMove = useCallback(
    (e: React.PointerEvent) => {
      if (!resizeStart.current) return;
      const s = actions();
      const p = s.panels[id];
      if (!p) return;
      const dx = e.clientX - resizeStart.current.x;
      const dy = e.clientY - resizeStart.current.y;
      s.setRect(id, {
        width: Math.max(240, resizeStart.current.w + dx),
        height: Math.max(160, resizeStart.current.h + dy),
      });
    },
    [id, actions],
  );
  const onResizeUp = useCallback(() => {
    resizeStart.current = null;
  }, []);

  if (!panel) return null;

  const setMode = (mode: PanelMode) => {
    if (mode === "popout") {
      openPopoutFor(id);
      return;
    }
    actions().setMode(id, mode);
  };

  return (
    <>
      <div
        className={
          "shrink-0 flex items-center gap-2 px-2.5 py-1.5 " +
          "border-b-edge border-sun bg-ice-1 dark:bg-charcoal-2 " +
          (draggable ? `cursor-grab active:cursor-grabbing select-none shadow-z1 dark:shadow-z1-night ${press} ` : "") +
          (focused ? "" : "opacity-90")
        }
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {/* Drag grip — only visible/meaningful in floating mode */}
        {draggable && (
          <span
            aria-hidden="true"
            className="font-mono text-ink-mute dark:text-moonlight leading-none"
          >
            ⋮⋮
          </span>
        )}

        {/* Title — flex-1 so the action cluster pins right */}
        <span className="flex-1 text-[12.5px] font-mono font-semibold truncate text-ink dark:text-bright">
          {panel.title}
        </span>

        {/* Pin toggle */}
        <button
          type="button"
          data-handle-action="pin"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => (panel.pinned ? actions().unpin(id) : actions().pin(id))}
          aria-label={panel.pinned ? "Unpin" : "Pin"}
          className={
            "px-1.5 leading-none text-[13px] " +
            (panel.pinned
              ? "text-sun-deep dark:text-sun"
              : "text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright")
          }
        >
          {panel.pinned ? "★" : "☆"}
        </button>

        {/* Kebab — mode actions */}
        <div
          data-handle-action="kebab"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <LemonDropdown
            trigger={
              <LemonButton variant="tertiary" size="sm" aria-label="Panel actions">
                ⋯
              </LemonButton>
            }
            align="below-right"
          >
            {({ close }) => (
              <>
                <LemonMenuItem
                  icon="◧"
                  hint="⌘B"
                  onClick={() => {
                    emitWernerExperience("highlight"); setMode("docked-left");
                    close();
                  }}
                >
                  Dock left
                </LemonMenuItem>
                <LemonMenuItem
                  icon="◨"
                  hint="⇧⌘B"
                  onClick={() => {
                    emitWernerExperience("highlight"); setMode("docked-right");
                    close();
                  }}
                >
                  Dock right
                </LemonMenuItem>
                <LemonMenuItem
                  icon="◯"
                  hint="⌃⌘B"
                  onClick={() => {
                    emitWernerExperience("highlight"); setMode("docked-bottom");
                    close();
                  }}
                >
                  Dock bottom
                </LemonMenuItem>
                <LemonMenuItem
                  icon="▢"
                  hint="⌥⌘F"
                  onClick={() => {
                    emitWernerExperience("highlight"); setMode("floating");
                    close();
                  }}
                >
                  Float
                </LemonMenuItem>
                <LemonMenuItem
                  icon="↗"
                  hint="⌥⌘P"
                  onClick={() => {
                    emitWernerExperience("highlight"); setMode("popout");
                    close();
                  }}
                >
                  Pop out window
                </LemonMenuItem>
                <div className="my-1 border-t border-rule dark:border-charcoal-1" />
                <LemonMenuItem
                  icon="✕"
                  hint="⌘W"
                  onClick={() => {
                    actions().close(id);
                    close();
                  }}
                >
                  Close panel
                </LemonMenuItem>
              </>
            )}
          </LemonDropdown>
        </div>

        {/* Quick close */}
        <button
          type="button"
          data-handle-action="close"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => { emitWernerExperience("note_saved"); actions().close(id); }}
          aria-label="Close panel"
          className="px-1.5 leading-none text-[13px] text-ink-mute dark:text-moonlight hover:text-emperor"
        >
          ✕
        </button>
      </div>

      {/* Resize grip (bottom-right). Floating only.
          Uses `title` not `aria-label` — axe rejects aria-label on
          roleless divs (`aria-prohibited-attr`). A separator role
          requires aria-required-attr (valuenow/min/max). Resize
          grip isn't a true ARIA control; native `title` is the
          right semantic for a tooltip-only affordance. */}
      {resizable && panel.mode === "floating" && (
        <div
          title="Resize panel"
          onPointerDown={onResizeDown}
          onPointerMove={onResizeMove}
          onPointerUp={onResizeUp}
          onPointerCancel={onResizeUp}
          className="absolute right-0 bottom-0 w-4 h-4 cursor-nwse-resize z-10"
          style={{
            background:
              "linear-gradient(135deg, transparent 0%, transparent 50%, #F5DF24 50%, #F5DF24 60%, transparent 60%, transparent 70%, #F5DF24 70%, #F5DF24 80%, transparent 80%)",
          }}
        />
      )}
    </>
  );
}

export default PanelHandle;
