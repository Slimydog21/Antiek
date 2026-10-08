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
import { beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";

import {
  defaultDockedSize,
  initialFloatingRect,
  nextZ,
  reorderArray,
} from "./panelLayoutLogic";
import { EMPTY_SNAPSHOT } from "./panel.types";
import type {
  CockpitChrome,
  LayoutPreset,
  PanelDescriptor,
  PanelKind,
  PanelMode,
  PaneArrangement,
  PanePresentation,
  PaneSide,
  PaneTarget,
  WorkspaceSnapshot,
} from "./panel.types";
import { project, readPanePreferences, writeLayoutPreset, writePaneArrangement, writeScope } from "./persistence";
import type { PersistScope } from "./persistence";
import { CORE_PANE, COMPANION_PANE, adjacentPane, reconcilePaneOrder, reconcilePaneTiles,
  samePane, swapAdjacentPane, swapPaneTiles } from "./paneFlowGeometry";
import { registerWindowPresentationObserver, useWindows } from "./windowsStore";

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
  reorderDock: (side: "left" | "right" | "bottom", fromIndex: number, toIndex: number) => void;
  bringToFront: (id: string) => void;
  pin: (id: string) => void;
  unpin: (id: string) => void;
  /** Resize the bottom dock (px). Min 120, max 60% of viewport. */
  setDockBottomHeight: (height: number) => void;
  /** Cockpit chrome (C2): choose the layout recipe. Persists via its own
   *  global blob (persistence.ts) — a reload keeps the operator's choice. */
  setLayoutPreset: (preset: LayoutPreset) => void;
  /** docked ⇄ omarchy-inset (the layout.togglePreset key row). */
  toggleLayoutPreset: () => void;
  /** Mark the inset pane holding the focus ring (null clears). */
  setFocusedPane: (pane: PaneSide | null) => void;
  /** Set/clear the fullscreen pane directly (Esc restores via null). */
  setFullscreenPane: (pane: PaneSide | null) => void;
  /** Fullscreen the focused pane (default "left") or restore when one is
   *  already fullscreen — the pane.fullscreen key row. */
  toggleFullscreenPane: () => void;
  reset: () => void;
};

type PaneActions = {
  setPaneFocus: (target: PaneTarget | null) => boolean;
  reorderPane: (target: PaneTarget, direction: -1 | 1) => boolean;
  setPaneArrangement: (arrangement: PaneArrangement) => boolean;
  togglePaneArrangement: () => boolean;
  togglePaneZoom: (target: PaneTarget) => boolean;
  restorePaneZoom: () => boolean;
};

type Store = WorkspaceSnapshot & CockpitChrome & WorkspaceActions & PanePresentation & PaneActions
  & { panelCycleOrder: string[] };

const initialPanePreferences = readPanePreferences();

function rightPaneAdmitted(state: Pick<Store, "layoutPreset" | "dockRightIds" | "panels">): boolean {
  return state.layoutPreset === "omarchy-inset" || state.dockRightIds.some((id) =>
    Object.hasOwn(state.panels, id) && state.panels[id].mode !== "popout");
}

/** The right compound host exists exactly where the original tree mounts it.
 * Its panels remain inside that host; no panel becomes a product window. */
export function admittedPaneTargets(state: Pick<Store, "layoutPreset" | "dockRightIds" | "panels">): PaneTarget[] {
  const windows = useWindows.getState();
  return [CORE_PANE,
    ...(rightPaneAdmitted(state) ? [COMPANION_PANE] : []),
    ...windows.cycleOrder.filter((id) => Object.hasOwn(windows.windows, id))
      .map((id): PaneTarget => ({ kind: "window", id }))];
}

function reconcilePresentation(state: Store): Pick<PanePresentation, "paneOrder" | "paneTiles" | "paneFocus" | "paneZoom"> {
  const order = reconcilePaneOrder(state.paneOrder, admittedPaneTargets(state));
  const present = (target: PaneTarget | null): PaneTarget | null =>
    target && order.some((member) => samePane(member, target)) ? target : null;
  return { paneOrder: order, paneTiles: reconcilePaneTiles(state.paneTiles, order),
    paneFocus: present(state.paneFocus), paneZoom: present(state.paneZoom) };
}

const initialPaneOrder = admittedPaneTargets({ layoutPreset: initialPanePreferences.layoutPreset, dockRightIds: [], panels: {} });

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

/**
 * Would a panel in `mode` land where fullscreen is hiding it? The docked
 * preset's fullscreen collapses every dock; the inset's hides one pane (the
 * right pane holds the right dock, the left pane the left and bottom docks
 * and the floating layer). A panel the operator just asked for must show,
 * so opening one there restores the layout instead of mounting it into a
 * 0 px dock (F-18).
 */
function hiddenByFullscreen(s: CockpitChrome, mode: PanelMode): boolean {
  if (!s.fullscreenPane || mode === "popout") return false;
  if (s.layoutPreset === "docked") return mode !== "floating";
  return s.fullscreenPane === "left" ? mode === "docked-right" : mode !== "docked-right";
}

// Landing: main persists the resolved preset on startup (a fresh workspace's
// default included); the packet derives it from the migrated pane preferences.
// One source — the migrated value is what gets persisted.
writeLayoutPreset(initialPanePreferences.layoutPreset);

export const useWorkspace = create<Store>()((set, get) => ({
  ...EMPTY_SNAPSHOT,
  panelCycleOrder: [],
  // Explicit desktop preference migration preserves each valid old preset.
  // Pane order, tile splits, focus and zoom are transient client view state.
  layoutPreset: initialPanePreferences.layoutPreset,
  fullscreenPane: null,
  focusedPane: null,
  paneArrangement: initialPanePreferences.paneArrangement,
  paneOrder: initialPaneOrder,
  paneTiles: reconcilePaneTiles(null, initialPaneOrder),
  paneFocus: null,
  paneZoom: null,

  setPaneFocus: (target) => {
    const s = get();
    if (samePane(s.paneFocus, target)) return false;
    if (target && !admittedPaneTargets(s).some((member) => samePane(member, target))) return false;
    set({ paneFocus: target });
    return true;
  },

  reorderPane: (target, direction) => {
    const s = get();
    if (s.paneArrangement === "legacy" || s.paneZoom) return false;
    const order = reconcilePaneOrder(s.paneOrder, admittedPaneTargets(s));
    const neighbor = adjacentPane(order, target, direction);
    if (!neighbor) return false;
    set({ paneOrder: swapAdjacentPane(order, target, direction),
      paneTiles: swapPaneTiles(reconcilePaneTiles(s.paneTiles, order), target, neighbor) });
    return true;
  },

  setPaneArrangement: (arrangement) => {
    const s = get();
    if (arrangement === s.paneArrangement) return false;
    writePaneArrangement(arrangement);
    set({ paneArrangement: arrangement, paneZoom: null, fullscreenPane: null });
    return true;
  },

  togglePaneArrangement: () => get().setPaneArrangement(get().paneArrangement === "horizontal" ? "tiled" : "horizontal"),

  togglePaneZoom: (target) => {
    const s = get();
    if (s.paneArrangement === "legacy" || !admittedPaneTargets(s).some((member) => samePane(member, target))) return false;
    set({ paneZoom: samePane(s.paneZoom, target) ? null : target });
    return true;
  },

  restorePaneZoom: () => {
    if (!get().paneZoom) return false;
    set({ paneZoom: null });
    return true;
  },

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
        panelCycleOrder: mode === "popout" ? s.panelCycleOrder : [...s.panelCycleOrder, id],
        dockLeftIds: inserted.dockLeftIds ?? s.dockLeftIds,
        dockRightIds: inserted.dockRightIds ?? s.dockRightIds,
        dockBottomIds: inserted.dockBottomIds ?? s.dockBottomIds,
        floatingIds: inserted.floatingIds ?? s.floatingIds,
        zCounter: z,
        focusedPanelId: id,
        ...(hiddenByFullscreen(s, mode) ? { fullscreenPane: null } : {}),
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
        panelCycleOrder: s.panelCycleOrder.filter((member) => member !== id),
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

  setMode: (id, mode) =>
    set((s) => {
      const p = s.panels[id];
      if (!p) return s;
      const inserted = insertForMode(s, id, mode);
      const z = mode === "floating" ? nextZ(s.zCounter) : p.zIndex;
      return {
        ...s,
        panels: { ...s.panels, [id]: { ...p, mode, zIndex: z } },
        panelCycleOrder: mode === "popout" ? s.panelCycleOrder.filter((member) => member !== id)
          : s.panelCycleOrder.includes(id) ? s.panelCycleOrder : [...s.panelCycleOrder, id],
        dockLeftIds: inserted.dockLeftIds ?? s.dockLeftIds,
        dockRightIds: inserted.dockRightIds ?? s.dockRightIds,
        dockBottomIds: inserted.dockBottomIds ?? s.dockBottomIds,
        floatingIds: inserted.floatingIds ?? s.floatingIds,
        zCounter: mode === "floating" ? z : s.zCounter,
        focusedPanelId: id,
        ...(hiddenByFullscreen(s, mode) ? { fullscreenPane: null } : {}),
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

  setLayoutPreset: (preset) => {
    writeLayoutPreset(preset);
    // A preset swap clears the fullscreen state: the hidden pane's identity
    // is preset-relative, so carrying it across the swap could hide the
    // wrong area. Focused-pane ring state goes with it.
    set({ layoutPreset: preset, fullscreenPane: null, focusedPane: null });
  },

  toggleLayoutPreset: () => {
    get().setLayoutPreset(get().layoutPreset === "docked" ? "omarchy-inset" : "docked");
  },

  setFocusedPane: (pane) => set({ focusedPane: pane }),

  setFullscreenPane: (pane) => set({ fullscreenPane: pane }),

  toggleFullscreenPane: () => {
    const s = get();
    if (s.fullscreenPane) {
      set({ fullscreenPane: null });
      return;
    }
    // The docked preset's fullscreen collapses the docks; with none open it
    // would hide nothing and silently swallow the next panel (F-18), so it
    // is an honest no-op. The inset always has two panes on screen.
    if (
      s.layoutPreset === "docked" &&
      s.dockLeftIds.length + s.dockRightIds.length + s.dockBottomIds.length === 0
    ) {
      return;
    }
    set({ fullscreenPane: s.focusedPane ?? "left" });
  },

  // Wipe the workspace layout. The transient pane states clear with it (they
  // are ephemeral view state; leaking them into the next layout would hide
  // panes the operator never hid). The layout PRESET survives: it is the
  // operator's persisted chrome preference, not layout state — same standing
  // as custom hotkeys.
  //
  // G-X2: a reset is NOT persisted. The palette clears the saved layout key
  // and then resets; without the suppression below, this state change would
  // schedule a debounced snapshot of the EMPTY layout and write it back into
  // the very key just cleared (~250 ms later). Any write already pending for
  // the pre-reset layout is cancelled for the same reason.
  reset: () => {
    if (pendingWrite) {
      clearTimeout(pendingWrite);
      pendingWrite = null;
    }
    suppressPersistAfterReset = true;
    const order = admittedPaneTargets({ ...get(), dockRightIds: [] });
    // EMPTY_SNAPSHOT carries no paneArrangement; a reset must not leak the
    // previous arrangement into the next scenario/test (critique N2 on #3754).
    set({ ...EMPTY_SNAPSHOT, panelCycleOrder: [], fullscreenPane: null, focusedPane: null, paneArrangement: "legacy",
      paneOrder: order, paneTiles: reconcilePaneTiles(null, order), paneFocus: null, paneZoom: null });
  },
}));

registerWindowPresentationObserver((event) => {
  const current = useWorkspace.getState();
  const presentation = reconcilePresentation(current);
  useWorkspace.setState(event.kind === "open"
    ? { ...presentation, paneFocus: { kind: "window", id: event.id }, paneZoom: null }
    : presentation);
});

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
/** G-X2: swallow the one subscriber pass caused by `reset()` — see below. */
let suppressPersistAfterReset = false;

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

/**
 * Bumped each time the shell's hydration replaces the workspace with a stored
 * layout. A route's PanelHost compares it in its cleanup: when a newer
 * hydration has run (the route changed), that layout is authoritative, so
 * the outgoing host must not close panels in it, even ones sharing its
 * starter ids (MS-01, critic r1: a saved sidebar was reset to its default).
 */
let hydrationGeneration = 0;
export function markHydrated(): void {
  hydrationGeneration += 1;
  const state = useWorkspace.getState();
  const visible = [...state.dockLeftIds, ...state.floatingIds, ...state.dockBottomIds, ...state.dockRightIds];
  useWorkspace.setState({ panelCycleOrder: [...new Set(visible)].filter((id) =>
    Object.hasOwn(state.panels, id) && state.panels[id].mode !== "popout") });
}
export function getHydrationGeneration(): number {
  return hydrationGeneration;
}

beforeWorkspaceOwnerChange(() => {
  // Preserve the outgoing owner's last edit before cancelling its timer.
  const state = useWorkspace.getState();
  if (persistenceEnabled && (pendingWrite !== null || Object.keys(state.panels).length > 0)) {
    const snapshot = project(state);
    // Its old OS windows retire with the session. Returning to this owner
    // restores their panels in the main window instead of hiding them.
    snapshot.panels = Object.fromEntries(Object.entries(snapshot.panels).map(([id, panel]) => [id,
      panel.mode === "popout" ? { ...panel, mode: "floating" as const } : panel,
    ]));
    writeScope(activeScope, snapshot);
  }
  disablePersistence();
  markHydrated();
  useWorkspace.getState().reset();
});

useWorkspace.subscribe((state, prev) => {
  if (suppressPersistAfterReset) {
    suppressPersistAfterReset = false;
    return;
  }
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
  const owner = workspaceOwnerSession();
  const scope = activeScope;
  const snapshot = project(state);
  pendingWrite = setTimeout(() => {
    pendingWrite = null;
    if (isWorkspaceOwnerSession(owner)) writeScope(scope, snapshot);
  }, 250);
});

// Run after the retained persistence subscriber so reset suppression is
// consumed by the actual reset, not by this nested presentation update.
useWorkspace.subscribe((state, previous) => {
  if (rightPaneAdmitted(state) !== rightPaneAdmitted(previous)) {
    useWorkspace.setState(reconcilePresentation(state));
  }
});
