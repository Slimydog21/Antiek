/**
 * paneResizeMode.ts — SPR-01 M4 (R8/R9): the modal RESIZE mode.
 *
 * herdr's Resize mode (refs/omarchy-herdr.md B-rules, input.rs:1034-1062):
 * sticky until exit; h/j/k/l and the arrows nudge the focused pane's
 * nearest split by 0.05 of its parent (ratio, clamped 0.1–0.9 by the
 * geometry); Esc restores the pre-mode tree, Enter commits, and pressing
 * the entry binding again (with or without prefix) exits. This module holds
 * the mode state and owns the keyboard while it is active; the bar
 * (PaneModeBar.tsx) reads it; the geometry (paneFlowGeometry.ts) owns the
 * tree math.
 *
 * Admission (S11 kept): entering is refused from a text field, a dialog, a
 * hidden pane, a legacy arrangement, and while zoomed or maximized — the
 * handler (PaneFlowLayout.togglePaneResizeModeAt) runs the packet's
 * admission guards first. In the horizontal arrangement the mode opens but
 * the bar says the columns have no splits to nudge (the page's M4 note:
 * widths are measured columns there) and the nudge keys no-op.
 *
 * Modality, recorded: while the mode is active it owns PLAIN keys — the
 * mode's own keys act, every other plain key is swallowed (a modal mode is
 * not a filter). Modifier chords and the prefix keep their own layers (the
 * prefix is the house's other mode; prefix+r exits through the row).
 * Text fields keep their keys even mid-mode.
 */
import { create } from "zustand";

import { isLoneModifier } from "../components/hotkeys/keymap";
import { registerKeyboardOwner } from "./keyboardOwnership";
import type { PaneTarget, PaneTile } from "./panel.types";
import { useWorkspace } from "./WorkspaceStore";

interface PaneResizeModeState {
  active: boolean;
  /** The pane the mode resizes (the focused pane at entry). */
  target: PaneTarget | null;
  /** Horizontal arrangement: the columns are measured, so there is nothing
   *  to nudge — the bar says so. */
  columns: boolean;
  /** The tile tree at entry, restored verbatim by Esc. */
  preModeTiles: PaneTile | null;
  enter: (target: PaneTarget) => boolean;
  /** commit=true (Enter, the binding again) keeps the resized tree;
   *  commit=false (Esc) restores the pre-mode tree exactly. */
  exit: (commit: boolean) => boolean;
  nudge: (axis: "x" | "y", delta: number) => boolean;
  /** Test seam. */
  reset: () => void;
}

function textField(target: EventTarget | null): boolean {
  return target instanceof HTMLElement
    && (target.isContentEditable
      || Boolean(target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])")));
}

let removeKeyboardOwner: (() => void) | null = null;

function onModeKey(e: KeyboardEvent): void {
  const mode = usePaneResizeMode.getState();
  if (!mode.active) return;
  // Modifier chords and lone modifiers belong to their own layers; the mode
  // owns plain keys only.
  if (e.ctrlKey || e.metaKey || e.altKey || isLoneModifier(e)) return;
  // A text field keeps its keys even mid-mode (the prefix's own rule).
  if (textField(e.target)) return;
  const consume = () => {
    e.preventDefault();
    e.stopPropagation();
  };
  switch (e.key) {
    case "Escape":
      consume();
      mode.exit(false);
      return;
    case "Enter":
      consume();
      mode.exit(true);
      return;
    case "r":
      // The entry binding again — without the prefix — exits (herdr).
      consume();
      mode.exit(true);
      return;
    case "h":
    case "ArrowLeft":
      consume();
      mode.nudge("x", -0.05);
      return;
    case "l":
    case "ArrowRight":
      consume();
      mode.nudge("x", 0.05);
      return;
    case "k":
    case "ArrowUp":
      consume();
      mode.nudge("y", -0.05);
      return;
    case "j":
    case "ArrowDown":
      consume();
      mode.nudge("y", 0.05);
      return;
    default:
      // Every other plain key is swallowed and the mode stays (modal, herdr).
      consume();
  }
}

export const usePaneResizeMode = create<PaneResizeModeState>()((set, get) => ({
  active: false,
  target: null,
  columns: false,
  preModeTiles: null,

  enter: (target) => {
    const s = useWorkspace.getState();
    if (get().active) return false;
    if (s.paneArrangement === "legacy" || s.paneZoom || s.paneMaximize) return false;
    set({ active: true, target, columns: s.paneArrangement === "horizontal", preModeTiles: s.paneTiles });
    removeKeyboardOwner = registerKeyboardOwner(
      window,
      {
        id: "pane.resizeMode",
        scope: "overlay",
        capture: true,
        eligible: (e) => get().active && !e.isComposing && !e.defaultPrevented,
      },
      onModeKey,
    );
    return true;
  },

  exit: (commit) => {
    const state = get();
    if (!state.active) return false;
    if (!commit && state.preModeTiles !== null) {
      useWorkspace.getState().restorePaneTiles(state.preModeTiles);
    }
    set({ active: false, target: null, columns: false, preModeTiles: null });
    removeKeyboardOwner?.();
    removeKeyboardOwner = null;
    return true;
  },

  nudge: (axis, delta) => {
    const s = get();
    if (!s.active || s.columns || !s.target) return false;
    return useWorkspace.getState().resizePaneTileRatio(s.target, axis, delta);
  },

  reset: () => {
    if (get().active) get().exit(true);
    set({ active: false, target: null, columns: false, preModeTiles: null });
  },
}));
