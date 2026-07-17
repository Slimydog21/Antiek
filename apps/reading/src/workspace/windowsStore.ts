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
 *
 * ── AMS2-SPR-04: windows are now the DEFAULT for within-contract pages ──
 * As of the mountain-shell-v2 work, opening a window is no longer a buried,
 * additive affordance — a within-contract default click (a product sub-action,
 * a reference-like page such as Stats/Library) lands as a floating window over
 * the scene. The policy INVERSION lives where the next reader looks:
 * `components/windows/openWindow.ts` (the policy comment) and
 * `components/windows/README.md`. This store is the same; the change is that
 * its guarantees are now load-bearing on the hot path, not an optional extra.
 * Two guarantees matter most for the default flow:
 *   - Bounded fan-out (MAX_WINDOWS, below) — a default click can never blow
 *     past the cap; at the cap, open() FOCUSES the oldest and returns its id
 *     (no phantom window, caller sees a real id).
 *   - Focus restack — newest-focused window is topmost; closing the focused
 *     window refocuses the next-topmost (or null when none remain), so the
 *     keyboard target is never orphaned.
 *
 * ── Persistence: in-memory, session-scoped (DELIBERATE) ──
 * There is NO persist middleware. Window state lives only in memory for the
 * life of the tab: a reload starts with ZERO windows (EMPTY below). This is a
 * choice, not an oversight. Workspace windows are an ephemeral arrangement of
 * the operator's current task ("multiple terminals" laid out right now), not a
 * saved document; persisting stale floating geometry/payloads across reloads
 * would resurrect windows pointing at since-changed routes/assets and surprise
 * the operator more than it helps. If persistence is later desired it is a
 * NAMED future task, NOT a silent assumption: wrap `useWindows` with zustand's
 * `persist` middleware keyed on the restorable subset of each descriptor —
 * `{ kind, payload, rect, mode }` — and rehydrate through `open()` so the cap
 * and z-restack invariants still hold (do NOT rehydrate `z`/`order`/`zCounter`
 * verbatim — replay opens so the monotonic counter and bound are respected).
 */

import { create } from "zustand";

import { cascadeOffset } from "../design/elevation";
import { zIndex } from "../design/zIndex";

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
  /** At the hard cap, replace the oldest window instead of redirecting this
   * exact-identity open to an unrelated surface. Opt-in because replacement
   * is appropriate only when showing the requested asset is load-bearing. */
  replaceOldestAtLimit?: boolean;
  /** Window ids that cap replacement must not evict (for example, the reader
   * currently initiating a child research window). */
  preserveIdsAtLimit?: readonly string[];
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
 *
 * Now that a default within-contract click opens a window (AMS2-SPR-04), this
 * bound is the hard backstop on the hot path: a rapid run of default activations
 * cannot exceed 8 windows — at the cap, open() focuses the oldest and returns
 * its id (see open() below). Kept at 8 deliberately; do NOT change the value or
 * the at-cap action shape without recording a new reason here and in
 * components/windows/README.md.
 */
export const MAX_WINDOWS = 8;

/** Base z so a window always paints over the scene (z≈0) but under the
 *  in-page modal/toast stack (LemonModal z=100). Sourced from the named
 *  z-index ladder (`zIndex.windowBase`) — re-exported under this name for
 *  back-compat (windowsStore.test.ts and callers import `WINDOW_Z_BASE`).
 *  Value is unchanged: still 40. */
export const WINDOW_Z_BASE = zIndex.windowBase;

/** Initial (and reset) state. With no persist middleware this is also the
 *  state every page LOAD starts in — a reload = zero windows, by design (see
 *  the persistence note in the file docblock). */
const EMPTY: WindowsSnapshot = {
  windows: {},
  order: [],
  focusedId: null,
  zCounter: WINDOW_Z_BASE,
};

export const DEFAULT_WINDOW_RECT: Readonly<WindowRect> = {
  x: 96,
  y: 88,
  width: 720,
  height: 520,
};

function uniqueId(prefix: string): string {
  return `win:${prefix}:${Math.random().toString(36).slice(2, 10)}`;
}

/** Cascade each new window down-right of the previous (elevation contract). */
function cascadeRect(n: number): WindowRect {
  const off = cascadeOffset(n, "windows");
  return {
    ...DEFAULT_WINDOW_RECT,
    x: DEFAULT_WINDOW_RECT.x + off.x,
    y: DEFAULT_WINDOW_RECT.y + off.y,
  };
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
    if (get().order.length >= MAX_WINDOWS && !opts.replaceOldestAtLimit) {
      const oldest = get().order[0];
      if (oldest) get().focus(oldest);
      return oldest ?? id;
    }
    if (get().order.length >= MAX_WINDOWS) {
      const preserved = new Set(opts.preserveIdsAtLimit ?? []);
      const oldestReplaceable = get().order.find((existingId) => !preserved.has(existingId));
      if (!oldestReplaceable) {
        const oldest = get().order[0];
        if (oldest) get().focus(oldest);
        return oldest ?? id;
      }
      get().close(oldestReplaceable);
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
