/**
 * tabTreeStore.ts — the cockpit's document-tab trees over the pure model
 * (tabTree.ts, MS-04). One tree per mothership (research / writing /
 * reading), keyed by the current mode, persisted ONLY through a
 * TabTreeAdapter (the model's §1.6: never localStorage/sessionStorage).
 *
 * Persistence honesty: the default adapter is the model's IN-MEMORY one, so
 * trees are SESSION-scoped — a reload starts from the adapter's in-memory
 * rows (empty across a real reload). Lane B owns the HTTP adapter
 * (GET/PUT/allocate); `setTabTreeAdapter` is the seam, and every save goes
 * through the same snapshot + expected-version + rebase-after-409 path the
 * server adapter will drive, so swapping adapters changes no caller.
 *
 * Tabs are NAVIGATION state (tab ≠ branch): closing or pruning a tab never
 * touches the investigation/document it pointed at. public_number stays null
 * this wave — the model assigns one only from the server's allocate route,
 * which is lane B's; a null number is the lawful state until then.
 */
import { create } from "zustand";

import { toast } from "../components/lemon/LemonToast";
import {
  closeTab,
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  fromSnapshot,
  rebase,
  setActive,
  spawnChild,
  toSnapshot,
  undo,
  visitChild,
  type CloseMode,
  type Mothership,
  type SpawnInput,
  type TabNode,
  type TabOp,
  type TabTree,
  type TabTreeAdapter,
  type UndoToken,
} from "./tabTree";

/** The project the trees are filed under. Single-project until the
 *  workstation layer (lane B) owns real project ids — a named constant, not
 *  a secret default. */
export const TAB_PROJECT_ID = "default";

/** The pathological project id used in tests to exercise the load path. */
export type { Mothership, TabNode, TabTree, UndoToken };

export interface SpawnTabResult {
  ok: boolean;
  tabId?: string;
  hier?: string;
  error?: string;
}

interface TabTreeState {
  trees: Record<Mothership, TabTree | null>;
  /** Motherships whose initial adapter load has completed. */
  loaded: Record<Mothership, boolean>;
  /** The pending op log per mothership (replayed by rebase after a 409). */
  pendingOps: Record<Mothership, TabOp[]>;
  /** The tree-panel toggle (prefix t). */
  treePanelOpen: boolean;
  /** The tree panel's subtree focus (null = the whole tree). */
  subtreeFocusId: string | null;
  /** The most recent close's undo token — the strip's undo affordance. */
  lastUndo: UndoToken | null;
  adapter: TabTreeAdapter;

  setTabTreeAdapter: (adapter: TabTreeAdapter) => void;
  ensureMothership: (mothership: Mothership) => Promise<void>;
  spawnTab: (mothership: Mothership, parentId: string | null, input: SpawnInput) => SpawnTabResult;
  activateTab: (mothership: Mothership, tabId: string | null) => void;
  goToParent: (mothership: Mothership) => void;
  visitChildOfActive: (mothership: Mothership) => void;
  cycleSibling: (mothership: Mothership, direction: 1 | -1) => void;
  closeActiveTab: (mothership: Mothership, mode: CloseMode) => void;
  undoLastClose: (mothership: Mothership) => void;
  toggleTreePanel: () => void;
  setSubtreeFocus: (tabId: string | null) => void;
  /** Test seam. */
  resetTabTrees: () => void;
}

/** Serialize adapter saves per mothership (expected-version discipline). */
const saveQueues = new Map<Mothership, Promise<void>>();

function emptyLoaded(): Record<Mothership, boolean> {
  return { research: false, writing: false, reading: false };
}

export const useTabTrees = create<TabTreeState>()((set, get) => {
  /** Apply a pure-model op to a mothership's tree, keep the pending log,
   *  and queue the snapshot save. */
  function apply(
    mothership: Mothership,
    next: TabTree,
    op: TabOp,
  ): void {
    set((s) => ({
      trees: { ...s.trees, [mothership]: next },
      pendingOps: {
        ...s.pendingOps,
        [mothership]: [...(s.pendingOps[mothership] ?? []), op],
      },
    }));
    queueSave(mothership);
  }

  function queueSave(mothership: Mothership): void {
    const prior = saveQueues.get(mothership) ?? Promise.resolve();
    const run = prior.then(() => saveNow(mothership));
    saveQueues.set(mothership, run);
  }

  async function saveNow(mothership: Mothership): Promise<void> {
    const { adapter, trees, pendingOps } = get();
    const tree = trees[mothership];
    if (!tree) return;
    const result = await adapter.save(TAB_PROJECT_ID, mothership, toSnapshot(tree));
    if (result.status === "saved") {
      set((s) => ({
        trees: {
          ...s.trees,
          [mothership]: s.trees[mothership]
            ? { ...s.trees[mothership]!, version: result.version }
            : s.trees[mothership],
        },
        pendingOps: { ...s.pendingOps, [mothership]: [] },
      }));
      return;
    }
    if (result.status === "conflict") {
      // Another writer won. Rebase the pending ops onto the remote snapshot
      // (spawns are never lost; dead ops drop with one quiet toast) and save
      // once more. The in-memory adapter cannot produce this path in a single
      // tab; lane B's multi-device adapter can, and it is fully wired.
      const parsed = fromSnapshot(result.current);
      if (parsed.ok) {
        const { tree: rebased, dropped } = rebase(parsed.tree, pendingOps[mothership] ?? []);
        set((s) => ({
          trees: { ...s.trees, [mothership]: rebased },
          pendingOps: { ...s.pendingOps, [mothership]: [] },
        }));
        if (dropped.length > 0) {
          toast.info("A tab was closed on another device; your other changes were kept.");
        }
        const retry = await adapter.save(TAB_PROJECT_ID, mothership, toSnapshot(rebased));
        if (retry.status === "saved") {
          set((s) => ({
            trees: {
              ...s.trees,
              [mothership]: s.trees[mothership]
                ? { ...s.trees[mothership]!, version: retry.version }
                : s.trees[mothership],
            },
          }));
        }
      }
      return;
    }
    // "rejected" — the adapter refused the snapshot as invalid. The model's
    // own validation should make this unreachable; log honestly, never crash.
    // eslint-disable-next-line no-console
    console.error("[antiek/tabs] snapshot rejected:", result.reasons);
  }

  return {
    trees: { research: null, writing: null, reading: null },
    loaded: emptyLoaded(),
    pendingOps: { research: [], writing: [], reading: [] },
    treePanelOpen: false,
    subtreeFocusId: null,
    lastUndo: null,
    adapter: createInMemoryTabTreeAdapter(),

    setTabTreeAdapter: (adapter) =>
      set({
        adapter,
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        pendingOps: { research: [], writing: [], reading: [] },
      }),

    ensureMothership: async (mothership) => {
      if (get().loaded[mothership]) return;
      const snapshot = await get().adapter.load(TAB_PROJECT_ID, mothership);
      const parsed = fromSnapshot(snapshot);
      set((s) => ({
        trees: {
          ...s.trees,
          [mothership]: parsed.ok ? parsed.tree : emptyTabTree(mothership, snapshot.version),
        },
        loaded: { ...s.loaded, [mothership]: true },
      }));
    },

    spawnTab: (mothership, parentId, input) => {
      const tree = get().trees[mothership] ?? emptyTabTree(mothership);
      const result = spawnChild(tree, parentId, input);
      if (!result.ok) return { ok: false, error: result.error.message };
      apply(mothership, result.tree, result.op);
      set({ lastUndo: null });
      return { ok: true, tabId: input.tab_id, hier: result.tree.nodes[input.tab_id].hier_number };
    },

    activateTab: (mothership, tabId) => {
      const tree = get().trees[mothership];
      if (!tree) return;
      const result = setActive(tree, tabId);
      if (result.ok) apply(mothership, result.tree, result.op);
    },

    goToParent: (mothership) => {
      const tree = get().trees[mothership];
      const active = tree?.active_tab_id;
      if (!tree || !active) return;
      const parent = tree.nodes[active]?.parent_tab_id ?? null;
      if (parent === null) return; // a root has no parent — honest no-op
      get().activateTab(mothership, parent);
    },

    visitChildOfActive: (mothership) => {
      const tree = get().trees[mothership];
      const active = tree?.active_tab_id;
      if (!tree || !active) return;
      const result = visitChild(tree, active);
      if (result.ok) apply(mothership, result.tree, result.op);
      // no_children is an honest no-op, never an error surface
    },

    cycleSibling: (mothership, direction) => {
      const tree = get().trees[mothership];
      const active = tree?.active_tab_id;
      if (!tree || !active) return;
      const node = tree.nodes[active];
      if (!node) return;
      const siblings =
        node.parent_tab_id === null
          ? tree.root_order
          : (tree.nodes[node.parent_tab_id]?.child_order ?? []);
      if (siblings.length < 2) return; // nowhere to cycle — honest no-op
      const cur = siblings.indexOf(active);
      const next = (cur + direction + siblings.length) % siblings.length;
      get().activateTab(mothership, siblings[next]);
    },

    closeActiveTab: (mothership, mode) => {
      const tree = get().trees[mothership];
      const active = tree?.active_tab_id;
      if (!tree || !active) return;
      const result = closeTab(tree, active, mode, new Date().toISOString());
      if (!result.ok) return;
      set({ lastUndo: result.undo });
      apply(mothership, result.tree, result.op);
    },

    undoLastClose: (mothership) => {
      const tree = get().trees[mothership];
      const token = get().lastUndo;
      if (!tree || !token) return;
      const result = undo(tree, token);
      if (result.ok) {
        set({ lastUndo: null });
        apply(mothership, result.tree, result.op);
      } else {
        // The close was superseded; the token is dead — clear it honestly.
        set({ lastUndo: null });
      }
    },

    toggleTreePanel: () => set((s) => ({ treePanelOpen: !s.treePanelOpen })),
    setSubtreeFocus: (tabId) => set({ subtreeFocusId: tabId }),

    resetTabTrees: () =>
      set({
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        pendingOps: { research: [], writing: [], reading: [] },
        treePanelOpen: false,
        subtreeFocusId: null,
        lastUndo: null,
        adapter: createInMemoryTabTreeAdapter(),
      }),
  };
});
