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
 *
 * Close is HELD locally through the 10 s undo window (§2.2): the tree drops
 * the tab at once, a LemonToast offers Undo for UNDO_TTL_MS, and the close
 * joins the pending log (and so the next snapshot) only when the window
 * lapses. Saves wait while a close is held, so no snapshot other devices
 * read ever carries a close that was undone. A close lost to a reload
 * inside the window was never written: the tab is simply back.
 */
import { create } from "zustand";

import { toast, UNDO_TTL_MS } from "../components/lemon/LemonToast";
import { labelForTab } from "./tabLabels";
import { resetTabTitles, titleKey, useTabTitles } from "./tabTitles";
import { tabTreeHandle } from "./tabTreeHandle";
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

export type { Mothership, TabNode, TabTree, UndoToken };

/** A close inside its undo window, not yet in the pending log. */
export interface HeldClose {
  mothership: Mothership;
  token: UndoToken;
  op: TabOp;
}

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
  /** The last load failure per mothership (null = none). The raw message is
   *  for "Copy error details", never for the screen. */
  loadError: Record<Mothership, string | null>;
  /** The pending op log per mothership (replayed by rebase after a 409). */
  pendingOps: Record<Mothership, TabOp[]>;
  /** The tree-panel toggle (prefix t). */
  treePanelOpen: boolean;
  /** The tree panel's subtree focus (null = the whole tree). */
  subtreeFocusId: string | null;
  /** The close inside its 10 s window (written only when it lapses). */
  heldClose: HeldClose | null;
  adapter: TabTreeAdapter;

  setTabTreeAdapter: (adapter: TabTreeAdapter) => void;
  /** Load a mothership's tree once. Never rejects: a failure lands in
   *  loadError and retryLoad tries again. */
  ensureMothership: (mothership: Mothership) => Promise<void>;
  retryLoad: (mothership: Mothership) => Promise<void>;
  spawnTab: (mothership: Mothership, parentId: string | null, input: SpawnInput) => SpawnTabResult;
  activateTab: (mothership: Mothership, tabId: string | null) => void;
  goToParent: (mothership: Mothership) => void;
  visitChildOfActive: (mothership: Mothership) => void;
  cycleSibling: (mothership: Mothership, direction: 1 | -1) => void;
  closeActiveTab: (mothership: Mothership, mode: CloseMode) => void;
  /** Undo one close by its id: a held close is dropped without a write; a
   *  close already written is undone through the model (numbers reclaimed). */
  undoClose: (closeId: string) => void;
  undoLastClose: (mothership: Mothership) => void;
  toggleTreePanel: () => void;
  setSubtreeFocus: (tabId: string | null) => void;
  /** Test seam. */
  resetTabTrees: () => void;
}

/** Serialize adapter saves per mothership (expected-version discipline). */
const saveQueues = new Map<Mothership, Promise<void>>();
/** One in-flight load per mothership (the route sync and a cross-pane open
 *  can both ask on the same tick). */
const loads = new Map<Mothership, Promise<void>>();
/** Saves asked for while a close was held; run when the hold resolves. */
const deferredSaves = new Set<Mothership>();
let holdTimer: ReturnType<typeof setTimeout> | null = null;
/** Written closes still inside their toast's window, by close_id. */
const recentCloses = new Map<string, { mothership: Mothership; token: UndoToken }>();

function noErrors(): Record<Mothership, string | null> {
  return { research: null, writing: null, reading: null };
}

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
    if (get().heldClose) {
      deferredSaves.add(mothership);
      return;
    }
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

  /** The hold lapsed (or a newer close superseded it): the close joins the
   *  pending log and every save it deferred runs. */
  function commitHeld(): void {
    const held = get().heldClose;
    if (holdTimer !== null) clearTimeout(holdTimer);
    holdTimer = null;
    if (!held) return;
    set((s) => ({
      heldClose: null,
      pendingOps: {
        ...s.pendingOps,
        [held.mothership]: [...(s.pendingOps[held.mothership] ?? []), held.op],
      },
    }));
    recentCloses.set(held.token.close_id, { mothership: held.mothership, token: held.token });
    setTimeout(() => recentCloses.delete(held.token.close_id), UNDO_TTL_MS);
    deferredSaves.add(held.mothership);
    flushDeferred();
  }

  function flushDeferred(): void {
    const pending = [...deferredSaves];
    deferredSaves.clear();
    for (const m of pending) queueSave(m);
  }

  /** "Closed 1.3 · Lyell" / "Pruned 1.3 · Lyell and 4 tabs under it". */
  function closeMessage(tree: TabTree, tabId: string, mode: CloseMode, closedCount: number): string {
    const tab = tree.nodes[tabId];
    const parent = tab.parent_tab_id ? tree.nodes[tab.parent_tab_id] : null;
    const label = labelForTab(tab, parent, useTabTitles.getState().entries[titleKey(tab.kind, tab.ref)]).text;
    const name = `${tab.hier_number} · ${label}`;
    if (mode === "prune" && closedCount > 1) {
      const under = closedCount - 1;
      return `Pruned ${name} and ${under} tab${under === 1 ? "" : "s"} under it`;
    }
    return mode === "prune" ? `Pruned ${name}` : `Closed ${name}`;
  }

  return {
    trees: { research: null, writing: null, reading: null },
    loaded: emptyLoaded(),
    loadError: noErrors(),
    pendingOps: { research: [], writing: [], reading: [] },
    treePanelOpen: false,
    subtreeFocusId: null,
    heldClose: null,
    adapter: createInMemoryTabTreeAdapter(),

    setTabTreeAdapter: (adapter) => {
      loads.clear();
      set({
        adapter,
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
      });
    },

    ensureMothership: (mothership) => {
      if (get().loaded[mothership]) return Promise.resolve();
      const inflight = loads.get(mothership);
      if (inflight) return inflight;
      const adapter = get().adapter;
      let run: Promise<void> | null = null;
      run = (async () => {
        try {
          const snapshot = await adapter.load(TAB_PROJECT_ID, mothership);
          if (get().adapter !== adapter) return; // swapped mid-flight
          const parsed = fromSnapshot(snapshot);
          set((s) => ({
            trees: {
              ...s.trees,
              [mothership]: parsed.ok ? parsed.tree : emptyTabTree(mothership, snapshot.version),
            },
            loaded: { ...s.loaded, [mothership]: true },
            loadError: { ...s.loadError, [mothership]: null },
          }));
        } catch (e) {
          if (get().adapter !== adapter) return;
          set((s) => ({
            loadError: { ...s.loadError, [mothership]: e instanceof Error ? e.message : String(e) },
          }));
        } finally {
          if (loads.get(mothership) === run) loads.delete(mothership);
        }
      })();
      loads.set(mothership, run);
      return run;
    },

    retryLoad: (mothership) => {
      set((s) => ({ loadError: { ...s.loadError, [mothership]: null } }));
      return get().ensureMothership(mothership);
    },

    spawnTab: (mothership, parentId, input) => {
      const tree = get().trees[mothership] ?? emptyTabTree(mothership);
      const result = spawnChild(tree, parentId, input);
      if (!result.ok) return { ok: false, error: result.error.message };
      apply(mothership, result.tree, result.op);
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
      // One close is held at a time: a newer close writes the older one (its
      // toast's Undo still works, through the model's undo-after-write).
      commitHeld();
      const closedCount = Object.keys(tree.nodes).length - Object.keys(result.tree.nodes).length;
      const message = closeMessage(tree, active, mode, closedCount);
      set((s) => ({
        trees: { ...s.trees, [mothership]: result.tree },
        heldClose: { mothership, token: result.undo, op: result.op },
      }));
      holdTimer = setTimeout(commitHeld, UNDO_TTL_MS);
      const closeId = result.undo.close_id;
      toast.undo(message, () => get().undoClose(closeId));
    },

    undoClose: (closeId) => {
      const held = get().heldClose;
      if (held && held.token.close_id === closeId) {
        if (holdTimer !== null) clearTimeout(holdTimer);
        holdTimer = null;
        const tree = get().trees[held.mothership];
        const result = tree ? undo(tree, held.token) : null;
        set((s) => ({
          heldClose: null,
          ...(result?.ok ? { trees: { ...s.trees, [held.mothership]: result.tree } } : {}),
        }));
        // The close and its undo were never written; the other ops made in
        // the window were, just late.
        flushDeferred();
        return;
      }
      const recent = recentCloses.get(closeId);
      if (!recent) return;
      recentCloses.delete(closeId);
      const tree = get().trees[recent.mothership];
      if (!tree) return;
      const result = undo(tree, recent.token);
      if (result.ok) apply(recent.mothership, result.tree, result.op);
      else toast.info("That close can no longer be undone: the tree changed since.");
    },

    undoLastClose: (mothership) => {
      const held = get().heldClose;
      if (held && held.mothership === mothership) {
        get().undoClose(held.token.close_id);
        return;
      }
      const last = [...recentCloses.entries()].reverse().find(([, r]) => r.mothership === mothership);
      if (last) get().undoClose(last[0]);
    },

    toggleTreePanel: () => set((s) => ({ treePanelOpen: !s.treePanelOpen })),
    setSubtreeFocus: (tabId) => set({ subtreeFocusId: tabId }),

    resetTabTrees: () => {
      if (holdTimer !== null) clearTimeout(holdTimer);
      holdTimer = null;
      loads.clear();
      deferredSaves.clear();
      recentCloses.clear();
      saveQueues.clear();
      resetTabTitles();
      set({
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
        treePanelOpen: false,
        subtreeFocusId: null,
        heldClose: null,
        adapter: createInMemoryTabTreeAdapter(),
      });
    },
  };
});

// The keyboard dispatcher (entry chunk) reaches the store through this
// handle; the store itself loads with the lazy strip.
tabTreeHandle.store = useTabTrees;
