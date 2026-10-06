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
 * lapses. A save waits while a close is held (checked when it RUNS, so a
 * save queued before the close waits too), so no snapshot other devices
 * read ever carries a close that was undone. A close lost to a reload
 * inside the window was never written: the tab is simply back.
 */
import { create } from "zustand";

import { toast, UNDO_TTL_MS } from "../components/lemon/LemonToast";
import { clearTabProject, readTabProject, writeTabProject } from "./persistence";
import { labelForTab } from "./tabLabels";
import { resetTabTitles, titleKey, useTabTitles } from "./tabTitles";
import { tabTreeHandle } from "./tabTreeHandle";
import {
  acknowledgeRestores,
  closeTab,
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  fromSnapshot,
  lastRetired,
  rebase,
  restoreClosed,
  setActive,
  spawnChild,
  toSnapshot,
  undo,
  visitChild,
  type CloseMode,
  type Mothership,
  type SpawnInput,
  type SaveResult,
  type TabNode,
  type TabOp,
  type TabTree,
  type TabTreeAdapter,
  type UndoToken,
} from "./tabTree";

/** The project the trees are filed under when the operator has not chosen
 *  one. The account projects come from the registry (lib/api/projects.ts,
 *  THREAD-CONTRACT §1.5); the selection lives in the store's `projectId`
 *  (persisted via persistence.readTabProject) and every load/save files
 *  under it. This constant is the fallback id, a named constant, not a
 *  secret default. */
export const TAB_PROJECT_ID = "default";

/** CR-F3: how many rebase-and-save attempts follow the first 409 before the
 *  store stops and says so honestly. Intent is never dropped either way. */
const MAX_CONFLICT_RETRIES = 2;

export type { Mothership, TabNode, TabTree, UndoToken };

/** A close inside its undo window, not yet in the pending log. */
export interface HeldClose {
  mothership: Mothership;
  token: UndoToken;
  op: TabOp;
  expiresAt: number;
}

/**
 * Who asked for an activation. Only a USER activation (a strip click, a
 * tab key, an opener such as the cross-pane seam) navigates; the route →
 * tree sync ("route") follows a navigation that already happened, and
 * never starts one. Navigation is emitted by the command, never inferred
 * from whichever tab happens to be active (F-04: an inferring tree → route
 * effect hijacked every navigation after a mode switch or a reload).
 */
export type ActivationSource = "user" | "route";

/** A user activation's request to show its tab (the strip consumes it and
 *  navigates only when the route does not already show the tab). A null
 *  tabId is the close of the tree's last open tab: show the mode's home, so
 *  the screen and the strip agree (lane A B2-4). */
export interface NavIntent {
  mothership: Mothership;
  tabId: string | null;
  seq: number;
  /** The history entry it was issued at (locationStamp): an intent is
   *  shown only while the operator is still there. */
  at: string;
}

/** The current history entry: path, query and the router's entry key
 *  (BrowserRouter keeps it in history.state; a router that does not leaves
 *  the path and query to tell entries apart). */
export function locationStamp(): string {
  if (typeof window === "undefined") return "";
  const state = window.history.state as { key?: unknown } | null;
  const key = state && typeof state.key === "string" ? state.key : "";
  return `${window.location.pathname}${window.location.search}#${key}`;
}

export interface SpawnTabResult {
  ok: boolean;
  tabId?: string;
  hier?: string;
  error?: string;
}

interface TabTreeState {
  /** Invalidates in-flight work even when the same adapter is selected again. */
  contextEpoch: number;
  /** The account project every load/save files under (the adapter's first
   *  argument). TAB_PROJECT_ID until the operator picks one of the
   *  registry's projects (the project picker, prefix+shift+p). */
  projectId: string;
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
  /** The last user activation not yet shown (null = none pending). */
  navIntent: NavIntent | null;
  adapter: TabTreeAdapter;

  setTabTreeAdapter: (adapter: TabTreeAdapter) => void;
  /** Switch the account project the trees file under (the D2 project
   *  level). Persisted; the trees reset exactly as on an adapter swap and
   *  load again under the new id, so each project's tabs are its own. A
   *  re-select of the current project is a no-op. */
  selectProject: (projectId: string) => void;
  /** Load a mothership's tree once. Never rejects: a failure lands in
   *  loadError and retryLoad tries again. */
  ensureMothership: (mothership: Mothership) => Promise<void>;
  retryLoad: (mothership: Mothership) => Promise<void>;
  spawnTab: (
    mothership: Mothership,
    parentId: string | null,
    input: SpawnInput,
    source?: ActivationSource,
  ) => SpawnTabResult;
  activateTab: (mothership: Mothership, tabId: string | null, source?: ActivationSource) => void;
  /** The strip took the intent `seq` (a newer one stays pending). */
  consumeNavIntent: (seq: number) => void;
  goToParent: (mothership: Mothership) => void;
  visitChildOfActive: (mothership: Mothership) => void;
  cycleSibling: (mothership: Mothership, direction: 1 | -1) => void;
  closeActiveTab: (mothership: Mothership, mode: CloseMode) => void;
  /** Close any open tab (the tree panel's Delete / Shift+Delete). Held for
   *  the 10 s window exactly like closeActiveTab. */
  closeTabById: (mothership: Mothership, tabId: string, mode: CloseMode) => void;
  /** Undo one close by its id: a held close is dropped without a write; a
   *  close already written is undone through the model (numbers reclaimed). */
  undoClose: (closeId: string) => void;
  /** prefix+shift+t (lane A B2-6): the keyboard's undo for a close. Inside
   *  the 10 s hold (or while a written close's toast still offers Undo) it
   *  is that Undo, exactly; after it, the most recently retired tab of this
   *  tree comes back from history with its numbers (restoreClosed). False
   *  when there is nothing to reopen. */
  undoLastClose: (mothership: Mothership) => boolean;
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
/** The toast offering Undo for each close still undoable, by close_id, so a
 *  keyboard undo takes the toast away with the close. */
const undoToasts = new Map<string, number>();
let navSeq = 0;
/** Written closes still inside their toast's window, by close_id. */
const recentCloses = new Map<string, { mothership: Mothership; token: UndoToken }>();

function noErrors(): Record<Mothership, string | null> {
  return { research: null, writing: null, reading: null };
}

function emptyLoaded(): Record<Mothership, boolean> {
  return { research: false, writing: false, reading: false };
}

export const useTabTrees = create<TabTreeState>()((set, get) => {
  // Only accepted server history can authorize a restore PUT. A close/undo
  // pair coalesced before saving is a cancellation, not a retired-node restore.
  const acceptedTrees = new Map<Mothership, TabTree>();

  function prepareRestores(mothership: Mothership, tree: TabTree): TabTree {
    if (!tree.restoring) return tree;
    const accepted = acceptedTrees.get(mothership);
    const nodes = { ...tree.nodes };
    const restoring = { ...tree.restoring };
    for (const id of Object.keys(restoring)) {
      if (!nodes[id]) continue;
      const retired = accepted?.history[id]?.node;
      if (retired) {
        nodes[id] = { ...nodes[id], pruned_at: retired.pruned_at };
        restoring[id] = retired;
      } else {
        const { pruned_at: _localClose, ...open } = nodes[id];
        nodes[id] = open;
        delete restoring[id];
      }
    }
    const next: TabTree = { ...tree, nodes, restoring };
    if (!Object.keys(restoring).length) delete next.restoring;
    return next;
  }

  /** Drop every in-flight and held piece of tree context: an adapter swap
   *  and a project switch both start from nothing. */
  function clearTreeContext(): void {
    loads.clear();
    acceptedTrees.clear();
    saveQueues.clear();
    deferredSaves.clear();
    recentCloses.clear();
    for (const id of undoToasts.values()) toast.dismiss(id);
    undoToasts.clear();
    if (holdTimer !== null) clearTimeout(holdTimer);
    holdTimer = null;
  }

  /** The blank per-context state slice (fresh objects, as emptyLoaded and
   *  noErrors return). */
  function freshTrees(): Pick<
    TabTreeState,
    "heldClose" | "navIntent" | "trees" | "loaded" | "loadError" | "pendingOps"
  > {
    return {
      heldClose: null,
      navIntent: null,
      trees: { research: null, writing: null, reading: null },
      loaded: emptyLoaded(),
      loadError: noErrors(),
      pendingOps: { research: [], writing: [], reading: [] },
    };
  }

  /** Apply a pure-model op to a mothership's tree, keep the pending log,
   *  and queue the snapshot save. */
  function apply(
    mothership: Mothership,
    next: TabTree,
    op: TabOp,
    navigate = false,
  ): void {
    set((s) => ({
      trees: { ...s.trees, [mothership]: next },
      pendingOps: {
        ...s.pendingOps,
        [mothership]: [...(s.pendingOps[mothership] ?? []), op],
      },
    }));
    // After the tree, so whoever reads the intent sees the tree it names.
    if (navigate) requestNav(mothership, next);
    queueSave(mothership);
  }

  /** A user activation asks the strip to show the tab it left active, or,
   *  when it left none (the last tab closed), the mode's home. */
  function requestNav(mothership: Mothership, next: TabTree): void {
    set({ navIntent: { mothership, tabId: next.active_tab_id, seq: ++navSeq, at: locationStamp() } });
  }

  function queueSave(mothership: Mothership): void {
    if (heldOn(mothership)) {
      deferredSaves.add(mothership);
      return;
    }
    const prior = saveQueues.get(mothership) ?? Promise.resolve();
    const contextEpoch = get().contextEpoch;
    const run = prior.then(() => get().contextEpoch === contextEpoch ? saveNow(mothership) : undefined);
    saveQueues.set(mothership, run);
  }

  function heldOn(mothership: Mothership): HeldClose | null {
    const held = get().heldClose;
    return held && held.mothership === mothership ? held : null;
  }

  /** Record a save's new version on the tree, and drop from the pending log
   *  the ops that save carried (ops made while it was in flight stay, for a
   *  later rebase). */
  function markSaved(mothership: Mothership, version: number, sentOps: number, sent: TabTree): void {
    acceptedTrees.set(mothership, acknowledgeRestores(sent, sent, version));
    set((s) => ({
      trees: {
        ...s.trees,
        [mothership]: s.trees[mothership] ? acknowledgeRestores(s.trees[mothership]!, sent, version) : s.trees[mothership],
      },
      pendingOps: { ...s.pendingOps, [mothership]: (s.pendingOps[mothership] ?? []).slice(sentOps) },
    }));
  }

  async function saveNow(mothership: Mothership): Promise<void> {
    // The hold is checked when the save RUNS, not when it was queued: a save
    // queued before a close would otherwise run inside the window and write
    // the close that the toast may yet undo (critic P-A). It waits instead,
    // and commitHeld/undoClose run it once the hold resolves.
    if (heldOn(mothership)) {
      deferredSaves.add(mothership);
      return;
    }
    const { adapter, trees, pendingOps, contextEpoch, projectId } = get();
    const currentTree = trees[mothership];
    if (!currentTree) return;
    const tree = prepareRestores(mothership, currentTree);
    if (tree !== currentTree) set((s) => ({ trees: { ...s.trees, [mothership]: tree } }));
    const sentOps = (pendingOps[mothership] ?? []).length;
    const result = await adapter.save(projectId, mothership, toSnapshot(tree));
    if (get().contextEpoch !== contextEpoch) return;
    if (result.status === "saved") {
      markSaved(mothership, result.version, sentOps, tree);
      return;
    }
    if (result.status === "conflict") {
      // Another writer won. Rebase the pending ops onto the remote snapshot
      // (spawns are never lost; dead ops drop with one quiet toast) and save
      // again. CR-F3: a retry that conflicts too REBASES onto that newer
      // snapshot and tries again, bounded — a second 409 never silently
      // drops the operator's intent (the base retried once and then left the
      // change pending with no further trigger). If every attempt is
      // refused, the intent STAYS in the pending log and the operator is
      // told honestly; the next action retries.
      let conflict: Extract<SaveResult, { status: "conflict" }> = result;
      for (let attempt = 1; attempt <= MAX_CONFLICT_RETRIES; attempt++) {
        const parsed = fromSnapshot(conflict.current);
        if (!parsed.ok) return;
        acceptedTrees.set(mothership, parsed.tree);
        // Every op made so far, including those made while the save was in
        // flight; a close still inside its window is not one of them.
        const ops = get().pendingOps[mothership] ?? [];
        const replayed = rebase(parsed.tree, ops);
        const { dropped, reparented } = replayed;
        const rebased = prepareRestores(mothership, replayed.tree);
        const notices = new Set<string>();
        for (const { tab_id, reason } of reparented) {
          const moved = rebased.nodes[tab_id];
          if (!moved) continue;
          const parent_tab_id = moved.parent_tab_id;
          const destination = parent_tab_id === null ? "to the root" : `under ${rebased.nodes[parent_tab_id].hier_number}`;
          const cause = reason === "closed_parent" ? "its parent was closed on another device" : "kept a tab added on another device";
          notices.add(`Moved ${destination}: ${cause}`);
        }
        for (const { reason } of dropped) {
          notices.add(reason === "tab_not_open" || reason === "unknown_tab"
            ? "A tab was closed on another device; your other changes were kept."
            : reason === "duplicate_tab_id"
              ? "A tab already exists on another device; your other changes were kept."
              : reason === "not_closed_by_token"
                ? "That close changed on another device; your other changes were kept."
                : "A tab change could not be applied to the updated tree; your other changes were kept.");
        }
        // A close held while the save was in flight stays held: it is replayed
        // onto the rebased tree for the screen only (same close_id, so its
        // toast's Undo still finds it), and the retry below writes the tree
        // WITHOUT it.
        const held = heldOn(mothership);
        let shown = rebased;
        if (held && held.op.type === "close") {
          const op = held.op;
          const replay = closeTab(rebased, op.tab_id, op.mode, op.now, op.close_id, op.seen_tab_ids);
          if (replay.ok) {
            shown = replay.tree;
            for (const node of Object.values(shown.nodes)) {
              if (op.mode !== "prune" || node.parent_tab_id === rebased.nodes[node.tab_id]?.parent_tab_id) continue;
              const destination = node.parent_tab_id === null ? "to the root" : `under ${shown.nodes[node.parent_tab_id].hier_number}`;
              notices.add(`Moved ${destination}: kept a tab added on another device`);
            }
            set({ heldClose: { ...held, token: replay.undo, op: replay.op } });
          } else {
            // Another device already closed it: nothing is left to hold.
            if (holdTimer !== null) clearTimeout(holdTimer);
            holdTimer = null;
            set({ heldClose: null });
          }
        }
        for (const notice of notices) toast.info(notice);
        const droppedOps = new Set(dropped.map(({ op }) => op));
        const remainingOps = ops.filter((op) => !droppedOps.has(op));
        set((s) => ({
          trees: { ...s.trees, [mothership]: shown },
          pendingOps: { ...s.pendingOps, [mothership]: remainingOps },
        }));
        const retry = await adapter.save(projectId, mothership, toSnapshot(rebased));
        if (get().contextEpoch !== contextEpoch) return;
        if (retry.status === "saved") {
          markSaved(mothership, retry.version, remainingOps.length, rebased);
          break;
        }
        if (retry.status === "rejected") {
          // eslint-disable-next-line no-console
          console.error("[antiek/tabs] snapshot rejected:", retry.reasons);
          break;
        }
        // Conflicted again: loop rebase onto THIS newer snapshot. When the
        // bound is spent the intent stays pending (never dropped) and the
        // operator is told the truth — it saves on their next action.
        if (attempt === MAX_CONFLICT_RETRIES) {
          toast.warn("Another writer keeps changing these tabs. Your change is kept here and saves on your next action.");
          break;
        }
        conflict = retry;
      }
      // The hold may have ended while the rebase was in flight.
      if (!heldOn(mothership)) flushDeferred();
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
    const closeId = held.token.close_id;
    const remaining = held.expiresAt - Date.now();
    if (remaining > 0) {
      recentCloses.set(closeId, { mothership: held.mothership, token: held.token });
      setTimeout(() => {
        recentCloses.delete(closeId);
        undoToasts.delete(closeId);
      }, remaining);
    } else {
      undoToasts.delete(closeId);
    }
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
    contextEpoch: 0,
    trees: { research: null, writing: null, reading: null },
    loaded: emptyLoaded(),
    loadError: noErrors(),
    pendingOps: { research: [], writing: [], reading: [] },
    treePanelOpen: false,
    subtreeFocusId: null,
    heldClose: null,
    navIntent: null,
    adapter: createInMemoryTabTreeAdapter(),
    projectId: readTabProject() ?? TAB_PROJECT_ID,

    setTabTreeAdapter: (adapter) => {
      clearTreeContext();
      set({
        ...freshTrees(),
        contextEpoch: get().contextEpoch + 1,
        adapter,
      });
    },

    selectProject: (projectId) => {
      if (get().projectId === projectId) return;
      // The full context swap, exactly as on an adapter change: trees filed
      // under one project are not another project's, so nothing carries
      // over. The default project is the absent selection (persistence).
      clearTreeContext();
      if (projectId === TAB_PROJECT_ID) clearTabProject();
      else writeTabProject(projectId);
      set({
        ...freshTrees(),
        contextEpoch: get().contextEpoch + 1,
        projectId,
      });
    },

    ensureMothership: (mothership) => {
      if (get().loaded[mothership]) return Promise.resolve();
      const inflight = loads.get(mothership);
      if (inflight) return inflight;
      const { adapter, contextEpoch, projectId } = get();
      let run: Promise<void> | null = null;
      run = (async () => {
        try {
          const snapshot = await adapter.load(projectId, mothership);
          if (get().contextEpoch !== contextEpoch) return; // swapped mid-flight
          const parsed = fromSnapshot(snapshot);
          if (parsed.ok) acceptedTrees.set(mothership, parsed.tree);
          set((s) => ({
            trees: {
              ...s.trees,
              [mothership]: parsed.ok ? parsed.tree : emptyTabTree(mothership, snapshot.version),
            },
            loaded: { ...s.loaded, [mothership]: true },
            loadError: { ...s.loadError, [mothership]: null },
          }));
        } catch (e) {
          if (get().contextEpoch !== contextEpoch) return;
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

    spawnTab: (mothership, parentId, input, source = "user") => {
      const tree = get().trees[mothership] ?? emptyTabTree(mothership);
      const result = spawnChild(tree, parentId, input);
      if (!result.ok) return { ok: false, error: result.error.message };
      apply(mothership, result.tree, result.op, source === "user" && input.activate === true);
      return { ok: true, tabId: input.tab_id, hier: result.tree.nodes[input.tab_id].hier_number };
    },

    activateTab: (mothership, tabId, source = "user") => {
      const tree = get().trees[mothership];
      if (!tree) return;
      const result = setActive(tree, tabId);
      // A user activation asks to be shown even when the tab was already
      // active: the route may have moved on (a click on the selected tab
      // from /library goes back to it).
      if (result.ok) apply(mothership, result.tree, result.op, source === "user");
    },

    consumeNavIntent: (seq) => {
      if (get().navIntent?.seq === seq) set({ navIntent: null });
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
      if (result.ok) apply(mothership, result.tree, result.op, true);
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
      const active = get().trees[mothership]?.active_tab_id;
      if (active) get().closeTabById(mothership, active, mode);
    },

    closeTabById: (mothership, active, mode) => {
      const tree = get().trees[mothership];
      if (!tree || !Object.hasOwn(tree.nodes, active)) return;
      const result = closeTab(tree, active, mode, new Date().toISOString());
      if (!result.ok) return;
      // One close is held at a time: a newer close writes the older one (its
      // toast's Undo still works, through the model's undo-after-write).
      commitHeld();
      const closedCount = Object.keys(tree.nodes).length - Object.keys(result.tree.nodes).length;
      const message = closeMessage(tree, active, mode, closedCount);
      set((s) => ({
        trees: { ...s.trees, [mothership]: result.tree },
        heldClose: { mothership, token: result.undo, op: result.op, expiresAt: Date.now() + UNDO_TTL_MS },
      }));
      // Closing is a user command: show whichever tab it left active.
      if (result.tree.active_tab_id !== tree.active_tab_id) requestNav(mothership, result.tree);
      holdTimer = setTimeout(commitHeld, UNDO_TTL_MS);
      const closeId = result.undo.close_id;
      undoToasts.set(closeId, toast.undo(message, () => get().undoClose(closeId)));
    },

    undoClose: (closeId) => {
      // Whichever path undid it (the toast's button or the key), the toast's
      // offer is spent.
      const offer = undoToasts.get(closeId);
      if (offer !== undefined) {
        undoToasts.delete(closeId);
        toast.dismiss(offer);
      }
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
        if (result?.ok && tree && result.tree.active_tab_id !== tree.active_tab_id) {
          requestNav(held.mothership, result.tree);
        }
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
      const result = undo(tree, recent.token, true);
      if (result.ok) {
        apply(recent.mothership, result.tree, result.op, result.tree.active_tab_id !== tree.active_tab_id);
      }
      else toast.info("That close can no longer be undone: the tree changed since.");
    },

    undoLastClose: (mothership) => {
      const held = get().heldClose;
      if (held && held.mothership === mothership) {
        get().undoClose(held.token.close_id);
        return true;
      }
      const tree = get().trees[mothership];
      const last = [...recentCloses.entries()].reverse().find(([, r]) => r.mothership === mothership);
      // A written close whose toast still offers Undo: that exact Undo (it
      // knows the tab's old place among its siblings).
      if (last && tree && Object.hasOwn(tree.history, last[1].token.tab_id)) {
        get().undoClose(last[0]);
        return true;
      }
      if (!tree) return false;
      const retired = lastRetired(tree);
      if (retired === null) return false;
      const result = restoreClosed(tree, retired);
      if (!result.ok) return false;
      apply(mothership, result.tree, result.op, true);
      return true;
    },

    toggleTreePanel: () => set((s) => ({ treePanelOpen: !s.treePanelOpen })),
    setSubtreeFocus: (tabId) => set({ subtreeFocusId: tabId }),

    resetTabTrees: () => {
      if (holdTimer !== null) clearTimeout(holdTimer);
      holdTimer = null;
      loads.clear();
      deferredSaves.clear();
      recentCloses.clear();
      undoToasts.clear();
      saveQueues.clear();
      resetTabTitles();
      acceptedTrees.clear();
      set({
        contextEpoch: get().contextEpoch + 1,
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
        treePanelOpen: false,
        subtreeFocusId: null,
        heldClose: null,
        navIntent: null,
        adapter: createInMemoryTabTreeAdapter(),
      });
    },
  };
});

// The keyboard dispatcher (entry chunk) reaches the store through this
// handle; the store itself loads with the lazy strip.
tabTreeHandle.store = useTabTrees;
