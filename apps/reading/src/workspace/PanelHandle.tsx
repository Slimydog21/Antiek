import { useCallback, useRef } from "react";

import LemonButton from "../components/lemon/LemonButton";
import { LemonDropdown, LemonMenuItem } from "../components/lemon/LemonDropdown";
import { formatBinding } from "../components/hotkeys/bindings";
import { press } from "../design/motion";

import { useWorkspace } from "./WorkspaceStore";
import { clampRectToViewport } from "./panelLayoutLogic";
import { openPopoutFor } from "./popout";
import type { PanelMode } from "./panel.types";
import { panelFocusId } from "./panelFocusId";
import { escOverlayOpen, topModal } from "./escapeOverlay";

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

const titleAvailable = (title: HTMLElement) => title.isConnected && document.activeElement === title &&
  !title.closest('[hidden], [aria-hidden="true"], [inert]') && !topModal() &&
  !escOverlayOpen(title.closest('[role="region"]') ?? title);

function handleTitleKeyDown(event: React.KeyboardEvent<HTMLDivElement>, { id, draggable, resizable }: Required<Props>) {
  if (event.target !== event.currentTarget || !titleAvailable(event.currentTarget) ||
      event.defaultPrevented || event.nativeEvent.isComposing || event.getModifierState("AltGraph") ||
      event.ctrlKey || event.metaKey || event.altKey) return;
  const current = useWorkspace.getState();
  if (!Object.hasOwn(current.panels, id)) return;
  const live = current.panels[id];
  if (live.mode !== "floating" || (event.shiftKey ? !resizable : !draggable)) return;
  let dx = 0, dy = 0;
  switch (event.key) {
    case "ArrowLeft": dx = -24; break;
    case "ArrowRight": dx = 24; break;
    case "ArrowUp": dy = -24; break;
    case "ArrowDown": dy = 24; break;
    default: return;
  }
  event.preventDefault();
  if (event.shiftKey) {
    current.setRect(id, { width: Math.max(240, live.rect.width + dx), height: Math.max(160, live.rect.height + dy) });
  } else {
    const rect = clampRectToViewport({ ...live.rect, x: live.rect.x + dx, y: live.rect.y + dy },
      { width: window.innerWidth, height: window.innerHeight });
    current.setRect(id, { x: rect.x, y: rect.y });
  }
}

function panelTitleHints(mode: PanelMode, draggable: boolean, resizable: boolean) {
  const move = mode === "floating" && draggable;
  const resize = mode === "floating" && resizable;
  const help = [move ? "Arrow keys move 24 pixels." : "", resize ? "Shift and arrow keys resize 24 pixels." : ""].filter(Boolean).join(" ");
  const shortcuts = [move ? "ArrowLeft ArrowRight ArrowUp ArrowDown" : "", resize ? "Shift+ArrowLeft Shift+ArrowRight Shift+ArrowUp Shift+ArrowDown" : ""].filter(Boolean).join(" ");

  return { help, shortcuts };
}

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

  const onTitleFocus = (event: React.FocusEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || !titleAvailable(event.currentTarget)) return;
    const current = actions();
    if (Object.hasOwn(current.panels, id) && current.focusedPanelId !== id) current.focus(id);
  };

  const onTitleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) =>
    handleTitleKeyDown(event, { id, draggable, resizable });

  if (!panel) return null;

  const titleId = panelFocusId(id);
  const { help, shortcuts } = panelTitleHints(panel.mode, draggable, resizable);

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
        id={titleId}
        data-panel-title={id}
        role="group"
        aria-label={`${panel.title} — panel controls`}
        aria-describedby={help ? `${titleId}-help` : undefined}
        aria-keyshortcuts={shortcuts || undefined}
        tabIndex={0}
        onFocus={onTitleFocus}
        onKeyDown={onTitleKeyDown}
        className={
          "shrink-0 flex items-center gap-2 px-2.5 py-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun " +
          "border-b-edge border-sun bg-ice-1 dark:bg-charcoal-2 " +
          (draggable ? `cursor-grab active:cursor-grabbing select-none shadow-z1 dark:shadow-z1-night ${press} ` : "") +
          (focused ? "" : "opacity-90")
        }
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {help && <span id={`${titleId}-help`} className="sr-only">{help}</span>}
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
        <span className="flex-1 text-xs font-mono font-semibold truncate text-ink dark:text-bright">
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
            "px-1.5 leading-none text-sm " +
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
                {/* No hotkey hints here except the one binding that actually
                    exists: ⌘W closes the FOCUSED FLOATING panel (bindings.ts
                    `close-float`). ⇧⌘B/⌃⌘B/⌥⌘F/⌥⌘P were phantom hints with no
                    handler anywhere, and ⌘B belongs to the ProjectTree toggle
                    (bindings.ts `projecttree`) — advertising it on "Dock left"
                    was lying chrome. Mode switches stay click-only until a
                    real binding lands in shortcuts.ts + bindings.ts. */}
                <LemonMenuItem
                  icon="◧"
                  onClick={() => {
                    setMode("docked-left");
                    close();
                  }}
                >
                  Dock left
                </LemonMenuItem>
                <LemonMenuItem
                  icon="◨"
                  onClick={() => {
                    setMode("docked-right");
                    close();
                  }}
                >
                  Dock right
                </LemonMenuItem>
                <LemonMenuItem
                  icon="◯"
                  onClick={() => {
                    setMode("docked-bottom");
                    close();
                  }}
                >
                  Dock bottom
                </LemonMenuItem>
                <LemonMenuItem
                  icon="▢"
                  onClick={() => {
                    setMode("floating");
                    close();
                  }}
                >
                  Float
                </LemonMenuItem>
                <LemonMenuItem
                  icon="↗"
                  onClick={() => {
                    setMode("popout");
                    close();
                  }}
                >
                  Pop out window
                </LemonMenuItem>
                <div className="my-1 border-t border-rule dark:border-charcoal-1" />
                <LemonMenuItem
                  icon="✕"
                  hint={formatBinding("mod+w")}
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
          onClick={() => actions().close(id)}
          aria-label="Close panel"
          className="px-1.5 leading-none text-sm text-ink-mute dark:text-moonlight hover:text-emperor"
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
              "linear-gradient(135deg, transparent 0%, transparent 50%, var(--sun) 50%, var(--sun) 60%, transparent 60%, transparent 70%, var(--sun) 70%, var(--sun) 80%, transparent 80%)",
          }}
        />
      )}
    </>
  );
}

export default PanelHandle;
