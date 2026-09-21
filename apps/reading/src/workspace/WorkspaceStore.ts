/**
 * WorkspaceStore — Zustand store backing the workspace panel system.
 *
 * In-memory only in S3. URL + localStorage persistence + popout
 * cross-window sync land in S9. Until then a page reload resets state.
 *
 * Actions (every state change goes through one of these — never mutate
 * the snapshot directly):
 *
 *   open         (kind, props?, opts?) → id    create + insert a panel
 *   close        (id)                          remove a panel
 *   focus        (id)                          mark focused (+ raise if floating)
 *   setMode      (id, mode)                    move between docks / floating
 *   setRect      (id, rect)                    update floating position+size
 *   setSize      (id, size)                    update docked size hint
 *   reorderDock  (side, fromIdx, toIdx)        rearrange a dock stack
 *   bringToFront (id)                          z-bump a floating panel
 *   pin / unpin  (id)                          survive route changes (S9)
 *   reset        ()                            wipe everything
 *
 * Z-index conventions (see src/workspace/README.md). These are the named
 * layers of the single z-index ladder (`src/design/zIndex.ts`) — the floating
 * band starts at `zIndex.floatingPanelBase` (2) and the modal/toast ceilings
 * are `zIndex.modal` (100) / `zIndex.toast` (200):
 *
 *   Dock chrome:       z = 0
 *   Docked panels:     z = 1   (zIndex.raised)
 *   Floating panels:   z = 2…50 (zIndex.floatingPanelBase…floatingPanelCeiling, via zCounter)
 *   LemonModal:        z = 100 (zIndex.modal)
 *   LemonToast:        z = 200 (zIndex.toast)
 */

import { create } from "zustand";

import {
  defaultDockedSize,
  initialFloatingRect,
  nextZ,
  reorderArray,
} from "./panelLayoutLogic";
import { EMPTY_SNAPSHOT } from "./panel.types";
import type {
  PanelDescriptor,
  PanelKind,
  PanelMode,
  WorkspaceSnapshot,
} from "./panel.types";
import { project, writeScope } from "./persistence";
import type { PersistScope } from "./persistence";

export type OpenOptions = {
  mode?: PanelMode;
  title?: string;
  /** Override the auto-generated id (for stable per-instance panels). */
  id?: string;
};

export type WorkspaceActions = {
  open: (kind: PanelKind, props?: Record<string, unknown>, opts?: OpenOptions) => string;
  close: (id: string) => void;
  focus: (id: string) => void;
  /**
   * herdr transfer P0/P1 — zoom one panel to the full slot with persistent
   * chrome. Pass the same id again (or null) to exit. Zoom is a RUNTIME
   * focus mode: it is not part of WorkspaceSnapshot, so it never persists,
   * and route hydration exits it (setState carries zoomedPanelId: null).
   */
  toggleZoom: (id: string | null) => void;
  setMode: (id: string, mode: PanelMode) => void;
  setRect: (id: string, rect: Partial<PanelDescriptor["rect"]>) => void;
  setSize: (id: string, size: Partial<PanelDescriptor["size"]>) => void;
  reorderDock: (side: "left" | "right" | "bottom", fromIndex: number, toIndex: number) => void;
  bringToFront: (id: string) => void;
  pin: (id: string) => void;
  unpin: (id: string) => void;
  /** Resize the bottom dock (px). Min 120, max 60% of viewport. */
  setDockBottomHeight: (height: number) => void;
  reset: () => void;
};

type Store = WorkspaceSnapshot & {
  /** The panel currently zoomed to the full slot, or null when not zoomed. */
  zoomedPanelId: string | null;
} & WorkspaceActions;

function uniqueId(prefix: string): string {
  return `${prefix}:${Math.random().toString(36).slice(2, 10)}`;
}

/** Remove `id` from whichever array currently holds it. */
function removeFromAllArrays(s: WorkspaceSnapshot, id: string): Partial<WorkspaceSnapshot> {
  return {
    dockLeftIds: s.dockLeftIds.filter((x) => x !== id),
    dockRightIds: s.dockRightIds.filter((x) => x !== id),
    dockBottomIds: s.dockBottomIds.filter((x) => x !== id),
    floatingIds: s.floatingIds.filter((x) => x !== id),
  };
}

/** Insert `id` into the array matching `mode`. */
function insertForMode(
  s: WorkspaceSnapshot,
  id: string,
  mode: PanelMode,
): Partial<WorkspaceSnapshot> {
  const cleaned = removeFromAllArrays(s, id);
  switch (mode) {
    case "docked-left":
      return { ...cleaned, dockLeftIds: [...cleaned.dockLeftIds!, id] };
    case "docked-right":
      return { ...cleaned, dockRightIds: [...cleaned.dockRightIds!, id] };
    case "docked-bottom":
      return { ...cleaned, dockBottomIds: [...cleaned.dockBottomIds!, id] };
    case "floating":
      return { ...cleaned, floatingIds: [...cleaned.floatingIds!, id] };
    case "popout":
      // Popouts are tracked only by their entry in `panels` (and the
      // popout window owns rendering). They don't appear in any of the
      // in-tab arrays.
      return cleaned;
  }
}

export const useWorkspace = create<Store>()((set, get) => ({
  ...EMPTY_SNAPSHOT,
  zoomedPanelId: null,

  open: (kind, props = {}, opts = {}) => {
    const id = opts.id ?? uniqueId(kind);
    let createdId = id;
    set((s) => {
      // If a panel with this id already exists, focus it instead of duplicating.
      if (s.panels[id]) {
        return s;
      }
      const mode = opts.mode ?? "floating";
      const z = nextZ(s.zCounter);
      const desc: PanelDescriptor = {
        id,
        kind,
        props,
        mode,
        zIndex: z,
        rect: initialFloatingRect(s.floatingIds.length),
        size: defaultDockedSize(),
        pinned: false,
        title: opts.title ?? kind,
      };
      const inserted = insertForMode(s, id, mode);
      return {
        ...s,
        panels: { ...s.panels, [id]: desc },
        dockLeftIds: inserted.dockLeftIds ?? s.dockLeftIds,
        dockRightIds: inserted.dockRightIds ?? s.dockRightIds,
        dockBottomIds: inserted.dockBottomIds ?? s.dockBottomIds,
        floatingIds: inserted.floatingIds ?? s.floatingIds,
        zCounter: z,
        focusedPanelId: id,
      };
    });
    // Existing id path: focus instead of duplicate
    const current = get().panels[id];
    if (current && current.id === id && createdId === id) {
      if (!get().focusedPanelId || get().focusedPanelId !== id) {
        get().focus(id);
      }
    }
    return createdId;
  },

  close: (id) =>
    set((s) => {
      if (!s.panels[id]) return s;
      const { [id]: _gone, ...rest } = s.panels;
      const cleaned = removeFromAllArrays(s, id);
      return {
        ...s,
        panels: rest,
        zoomedPanelId: s.zoomedPanelId === id ? null : s.zoomedPanelId,
        dockLeftIds: cleaned.dockLeftIds!,
        dockRightIds: cleaned.dockRightIds!,
        dockBottomIds: cleaned.dockBottomIds!,
        floatingIds: cleaned.floatingIds!,
        focusedPanelId: s.focusedPanelId === id ? null : s.focusedPanelId,
      };
    }),

  focus: (id) => {
    const s = get();
    const p = s.panels[id];
    if (!p) return;
    if (p.mode === "floating") {
      // Bring to front + set focus.
      get().bringToFront(id);
    } else {
      set({ focusedPanelId: id });
    }
  },

  toggleZoom: (id) =>
    set((s) => {
      if (id === null || !s.panels[id]) {
        // Exit zoom (also covers a zoomed panel that no longer exists).
        return { ...s, zoomedPanelId: null };
      }
      if (s.zoomedPanelId === id) {
        // Same panel again = exit.
        return { ...s, zoomedPanelId: null };
      }
      return { ...s, zoomedPanelId: id, focusedPanelId: id };
    }),

  setMode: (id, mode) =>
    set((s) => {
      const p = s.panels[id];
      if (!p) return s;
      const inserted = insertForMode(s, id, mode);
      const z = mode === "floating" ? nextZ(s.zCounter) : p.zIndex;
      return {
        ...s,
        panels: { ...s.panels, [id]: { ...p, mode, zIndex: z } },
        dockLeftIds: inserted.dockLeftIds ?? s.dockLeftIds,
        dockRightIds: inserted.dockRightIds ?? s.dockRightIds,
        dockBottomIds: inserted.dockBottomIds ?? s.dockBottomIds,
        floatingIds: inserted.floatingIds ?? s.floatingIds,
        zCounter: mode === "floating" ? z : s.zCounter,
        focusedPanelId: id,
      };
    }),

  setRect: (id, rect) =>
    set((s) => {
      const p = s.panels[id];
      if (!p || p.mode !== "floating") return s;
      return {
        ...s,
        panels: { ...s.panels, [id]: { ...p, rect: { ...p.rect, ...rect } } },
      };
    }),

  setSize: (id, size) =>
    set((s) => {
      const p = s.panels[id];
      if (!p) return s;
      return {
        ...s,
        panels: { ...s.panels, [id]: { ...p, size: { ...p.size, ...size } } },
      };
    }),

  reorderDock: (side, fromIndex, toIndex) =>
    set((s) => {
      if (side === "left") {
        return { ...s, dockLeftIds: reorderArray(s.dockLeftIds, fromIndex, toIndex) };
      }
      if (side === "right") {
        return { ...s, dockRightIds: reorderArray(s.dockRightIds, fromIndex, toIndex) };
      }
      return { ...s, dockBottomIds: reorderArray(s.dockBottomIds, fromIndex, toIndex) };
    }),

  bringToFront: (id) =>
    set((s) => {
      if (!s.panels[id]) return s;
      const z = nextZ(s.zCounter);
      return {
        ...s,
        zCounter: z,
        focusedPanelId: id,
        panels: { ...s.panels, [id]: { ...s.panels[id], zIndex: z } },
        floatingIds: [...s.floatingIds.filter((x) => x !== id), id],
      };
    }),

  pin: (id) =>
    set((s) => {
      const p = s.panels[id];
      if (!p) return s;
      return { ...s, panels: { ...s.panels, [id]: { ...p, pinned: true } } };
    }),

  unpin: (id) =>
    set((s) => {
      const p = s.panels[id];
      if (!p) return s;
      return { ...s, panels: { ...s.panels, [id]: { ...p, pinned: false } } };
    }),

  setDockBottomHeight: (height) =>
    set(() => {
      const vh = typeof window !== "undefined" ? window.innerHeight : 800;
      const clamped = Math.max(120, Math.min(Math.floor(vh * 0.6), height));
      return { dockBottomHeight: clamped };
    }),

  reset: () => set({ ...EMPTY_SNAPSHOT, zoomedPanelId: null }),
}));

/**
 * Subscribe persistence: every time the workspace changes, write a
 * debounced (250 ms) snapshot to localStorage under the current scope.
 *
 * The scope is mutable — the AppShell-level hydration hook updates it
 * when the route or investigation id changes. Default scope is
 * "global" so that even unscoped writes have a home.
 *
 * Call `setPersistScope({...})` to retarget; `disablePersistence()` to
 * turn writes off entirely (used by tests + by the popout windows).
 */
let activeScope: PersistScope = { kind: "global" };
let persistenceEnabled = true;
let pendingWrite: ReturnType<typeof setTimeout> | null = null;

export function setPersistScope(scope: PersistScope): void {
  activeScope = scope;
}
export function getPersistScope(): PersistScope {
  return activeScope;
}
export function disablePersistence(): void {
  persistenceEnabled = false;
  if (pendingWrite) {
    clearTimeout(pendingWrite);
    pendingWrite = null;
  }
}
export function enablePersistence(): void {
  persistenceEnabled = true;
}

useWorkspace.subscribe((state, prev) => {
  if (!persistenceEnabled) return;
  // Cheap reference-equality check on the bits we care about — avoid
  // writing on every store mutation if the persisted slice didn't move.
  if (
    state.panels === prev.panels &&
    state.dockLeftIds === prev.dockLeftIds &&
    state.dockRightIds === prev.dockRightIds &&
    state.dockBottomIds === prev.dockBottomIds &&
    state.dockBottomHeight === prev.dockBottomHeight
  ) {
    return;
  }
  if (pendingWrite) clearTimeout(pendingWrite);
  pendingWrite = setTimeout(() => {
    pendingWrite = null;
    writeScope(activeScope, project(useWorkspace.getState()));
  }, 250);
});
