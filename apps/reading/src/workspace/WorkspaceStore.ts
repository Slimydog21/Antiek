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
 * Z-index conventions (see src/workspace/README.md):
 *
 *   Dock chrome:       z = 0
 *   Docked panels:     z = 1
 *   Floating panels:   z = 2…50 (via zCounter)
 *   LemonModal:        z = 100
 *   LemonToast:        z = 200
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
  setMode: (id: string, mode: PanelMode) => void;
  setRect: (id: string, rect: Partial<PanelDescriptor["rect"]>) => void;
  setSize: (id: string, size: Partial<PanelDescriptor["size"]>) => void;
  reorderDock: (side: "left" | "right", fromIndex: number, toIndex: number) => void;
  bringToFront: (id: string) => void;
  pin: (id: string) => void;
  unpin: (id: string) => void;
  reset: () => void;
};

type Store = WorkspaceSnapshot & WorkspaceActions;

function uniqueId(prefix: string): string {
  return `${prefix}:${Math.random().toString(36).slice(2, 10)}`;
}

/** Remove `id` from whichever array currently holds it. */
function removeFromAllArrays(s: WorkspaceSnapshot, id: string): Partial<WorkspaceSnapshot> {
  return {
    dockLeftIds: s.dockLeftIds.filter((x) => x !== id),
    dockRightIds: s.dockRightIds.filter((x) => x !== id),
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
        rect: initialFloatingRect(z),
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
        dockLeftIds: cleaned.dockLeftIds!,
        dockRightIds: cleaned.dockRightIds!,
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
      return { ...s, dockRightIds: reorderArray(s.dockRightIds, fromIndex, toIndex) };
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

  reset: () => set({ ...EMPTY_SNAPSHOT }),
}));
