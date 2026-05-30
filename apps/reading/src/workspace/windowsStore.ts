/**
 * windowsStore — SPR-09 multi-window slice.
 *
 * A SEPARATE Zustand store from WorkspaceStore (the docked/floating panel
 * system). The two are deliberately disjoint:
 *
 *   WorkspaceStore  — the IDE-style dock + floating *panels* inside a single
 *                     product page (sidebars, chat, notebook side rails…).
 *   windowsStore    — the operator's *workspace windows*: transparent,
 *                     ad-bordered frames that each HOST a whole product page
 *                     over the mountainscape, multipliable like a developer's
 *                     terminals (the operator's "multiple terminals" vision).
 *
 * Keeping it a new slice (not an edit to WorkspaceStore) keeps the
 * cross-sprint merge clean — SPR-09 owns this file outright.
 *
 * Window lifecycle is intentionally small and explicit. Every state change
 * goes through one action; never mutate a snapshot directly.
 *
 *   open        (kind, payload?, opts?) → id   create a window (floating)
 *   close       (id)                           remove a window; refocus next
 *   focus       (id)                           restack z to top + mark focused
 *   setRect     (id, rect)                     update floating position+size
 *   expand      (id)                           floating → full (remembers rect)
 *   restore     (id)                           full → floating (last rect)
 *   toggleMode  (id)                           expand ⇄ restore
 *   reset       ()                             wipe all windows
 *
 * Z-ordering: windows live ABOVE the scene but BELOW the in-page panel
 * floating layer's modals/toasts. A monotonic `zCounter` makes the most
 * recently focused window the topmost. The base is WINDOW_Z_BASE so a
 * window always sits over the scene (z≈0) yet under LemonModal (z=100).
 */

import { create } from "zustand";

/** A window hosts a product page identified by its route kind. The kind is a
 *  free string (the route key); openWindow.ts maps each to a renderer. We do
 *  NOT reuse PanelKind — a window hosts a *page*, not a panel surface. */
export type WindowKind = string;

export type WindowMode = "floating" | "full";

export type WindowRect = { x: number; y: number; width: number; height: number };

export type WorkspaceWindowDescriptor = {
  /** Stable id. */
  id: string;
  /** Which product page to host (route key → renderer in openWindow.ts). */
  kind: WindowKind;
  /** floating over the scene, or expanded to fill the working region. */
  mode: WindowMode;
  /** Floating geometry. Preserved across an expand→restore round-trip. */
  rect: WindowRect;
  /** z within the windows layer (relative to WINDOW_Z_BASE). */
  z: number;
  /** Operator-readable title rendered in the window's title bar. */
  title: string;
  /** Opaque payload handed to the hosted page (e.g. { documentId }). */
  payload: Record<string, unknown>;
};

export type WindowsSnapshot = {
  windows: Record<string, WorkspaceWindowDescriptor>;
  /** Bottom-to-top render order (last = topmost). Mirrors floating z. */
  order: string[];
  /** The focused window id (keyboard target + topmost), or null. */
  focusedId: string | null;
  /** Monotonic z source so newly focused windows sit above older ones. */
  zCounter: number;
};

export type OpenWindowOptions = {
  title?: string;
  /** Override the auto id (stable per-page-instance, e.g. one per documentId). */
  id?: string;
  /** Seed geometry; otherwise a cascade rect is chosen. */
  rect?: Partial<WindowRect>;
  /** Open already expanded to full. */
  mode?: WindowMode;
};

export type WindowsActions = {
  open: (kind: WindowKind, payload?: Record<string, unknown>, opts?: OpenWindowOptions) => string;
  close: (id: string) => void;
  focus: (id: string) => void;
  setRect: (id: string, rect: Partial<WindowRect>) => void;
  expand: (id: string) => void;
  restore: (id: string) => void;
  toggleMode: (id: string) => void;
  reset: () => void;
};

type Store = WindowsSnapshot & WindowsActions;

/**
 * Bounded fan-out. The operator can spin up several windows ("multiple
 * terminals") but a transparent, ad-bordered, scene-backed window is the
 * most expensive surface in the shell. Beyond this the perf budget (SPR-09
 * M7) and the operator's ability to tell windows apart both collapse, so we
 * cap hard and surface the cap honestly rather than silently dropping or
 * letting the count run away. 8 mirrors a developer's realistic terminal
 * fan-out and keeps the worst case (8 transparent frames + the animated
 * scene) inside the SPR-11 FPS budget.
 */
export const MAX_WINDOWS = 8;

/** Base z so a window always paints over the scene (z≈0) but under the
 *  in-page modal/toast stack (LemonModal z=100). */
export const WINDOW_Z_BASE = 40;

const EMPTY: WindowsSnapshot = {
  windows: {},
  order: [],
  focusedId: null,
  zCounter: WINDOW_Z_BASE,
};

const DEFAULT_RECT: WindowRect = { x: 96, y: 88, width: 720, height: 520 };

function uniqueId(prefix: string): string {
  return `win:${prefix}:${Math.random().toString(36).slice(2, 10)}`;
}

/** Cascade each new window ~28px down-right of the previous so a fresh
 *  window never lands exactly atop the last (matches the panel cascade feel). */
function cascadeRect(n: number): WindowRect {
  const step = (n * 28) % 224;
  return { ...DEFAULT_RECT, x: DEFAULT_RECT.x + step, y: DEFAULT_RECT.y + step };
}

export const useWindows = create<Store>()((set, get) => ({
  ...EMPTY,

  open: (kind, payload = {}, opts = {}) => {
    const id = opts.id ?? uniqueId(kind);
    // Re-opening an existing id focuses instead of duplicating (stable
    // per-instance windows, e.g. one window per documentId).
    if (get().windows[id]) {
      get().focus(id);
      return id;
    }
    // Bounded fan-out — at the cap, focus the oldest rather than exceeding it.
    // Returning the existing id keeps callers honest (no phantom new window).
    if (get().order.length >= MAX_WINDOWS) {
      const oldest = get().order[0];
      if (oldest) get().focus(oldest);
      return oldest ?? id;
    }
    set((s) => {
      const z = s.zCounter + 1;
      const desc: WorkspaceWindowDescriptor = {
        id,
        kind,
        mode: opts.mode ?? "floating",
        rect: { ...cascadeRect(s.order.length), ...opts.rect },
        z,
        title: opts.title ?? kind,
        payload,
      };
      return {
        windows: { ...s.windows, [id]: desc },
        order: [...s.order, id],
        focusedId: id,
        zCounter: z,
      };
    });
    return id;
  },

  close: (id) =>
    set((s) => {
      if (!s.windows[id]) return s;
      const { [id]: _gone, ...rest } = s.windows;
      const order = s.order.filter((x) => x !== id);
      // Focus returns to the next-topmost window (last in order) on close —
      // SPR-09 M8 focus management.
      const focusedId = s.focusedId === id ? (order[order.length - 1] ?? null) : s.focusedId;
      return { ...s, windows: rest, order, focusedId };
    }),

  focus: (id) =>
    set((s) => {
      if (!s.windows[id]) return s;
      const z = s.zCounter + 1;
      return {
        ...s,
        zCounter: z,
        focusedId: id,
        windows: { ...s.windows, [id]: { ...s.windows[id], z } },
        // Move to the top of the render order (last = topmost).
        order: [...s.order.filter((x) => x !== id), id],
      };
    }),

  setRect: (id, rect) =>
    set((s) => {
      const w = s.windows[id];
      if (!w) return s;
      return { ...s, windows: { ...s.windows, [id]: { ...w, rect: { ...w.rect, ...rect } } } };
    }),

  expand: (id) =>
    set((s) => {
      const w = s.windows[id];
      if (!w || w.mode === "full") return s;
      // The current rect is preserved in `rect`; restore() reads it back.
      return { ...s, windows: { ...s.windows, [id]: { ...w, mode: "full" } } };
    }),

  restore: (id) =>
    set((s) => {
      const w = s.windows[id];
      if (!w || w.mode === "floating") return s;
      return { ...s, windows: { ...s.windows, [id]: { ...w, mode: "floating" } } };
    }),

  toggleMode: (id) => {
    const w = get().windows[id];
    if (!w) return;
    if (w.mode === "floating") get().expand(id);
    else get().restore(id);
  },

  reset: () => set({ ...EMPTY }),
}));
