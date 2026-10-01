/**
 * tabTreeStore.ts — the cockpit's document-tab trees over the pure model
 * (tabTree.ts, MS-04). One tree per mothership (research / writing /
 * reading), keyed by the current mode, persisted ONLY through a
 * TabTreeAdapter (the model's §1.6: never localStorage/sessionStorage).
 *
 * Persistence honesty: `tabsPersistence` says which it is. The default
 * adapter is the model's IN-MEMORY one ("session": a reload starts empty).
 * `bindActiveProject` binds the trees to the active project's server row
 * through the HTTP adapter (tabTreeHttpAdapter.ts, lane B's LB-2 routes) and
 * reports "server"; when GET /projects answers 404, or a 200 that is not
 * JSON (the route is not deployed), it keeps the in-memory adapter and
 * reports "session", so the UI can say "Tabs aren't saved across reloads
 * yet"; a network error is retried first (1 s, 4 s, 15 s). Every save goes
 * through one path for both adapters: snapshot + expected version, adopt the
 * server's answer (replaying ops made in flight), rebase after a 409, and
 * after a 422 log, refetch, rebase and record that tree's `persistenceIssues`
 * entry (cleared only by the next accepted save of the same tree), so "server"
 * never claims tabs are saved while the server is refusing them (`tabsSaved`).
 *
 * Tabs are NAVIGATION state (tab ≠ branch): closing or pruning a tab never
 * touches the investigation/document it pointed at. New tabs receive their
 * public number from the adapter before their first snapshot is saved.
 * A failed allocation retains the tab and retries with the same ID.
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
import { ApiError } from "../lib/api";
import { listProjects } from "../lib/api/projects";
import { labelForTab } from "./tabLabels";
import { resetTabTitles, titleKey, useTabTitles } from "./tabTitles";
import { tabTreeHandle } from "./tabTreeHandle";
import {
  assignPublicNumber,
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
  type TabNode,
  type TabOp,
  type TabTree,
  type TabTreeAdapter,
  type TabTreeSnapshot,
  type UndoToken,
} from "./tabTree";
import { getTabOwner, subscribeTabOwner } from "./tabTreeOwner";
import { createHttpTabTreeAdapter } from "./tabTreeHttpAdapter";

/** The key the in-memory adapter files session trees under. It never
 *  reaches a server: a server-bound store uses the active project's id. */
export const SESSION_PROJECT_KEY = "default";

/** Where the trees are saved to: "session" (in memory, gone on reload) or
 *  "server" (the active project's row, §1.6). It claims the tabs ARE saved
 *  only after its work is acknowledged: see `tabsSaved`. */
export type TabsPersistence = "session" | "server";

/** The last save of `mothership`'s tree was refused (a 422: Part 2 §2.2
 *  calls it a lane-A bug). The store has already logged it, refetched and
 *  rebased, so the tabs are on screen but not saved. A later accepted save of
 *  that tree clears it. `at` is when the refusal came back (ISO 8601). */
export interface PersistenceIssue {
  reason: "refused" | "transport" | "conflict" | "unreadable";
  at: string;
  mothership: Mothership;
}

/** One slot per tree: a refusal of one tree is never overwritten or cleared
 *  by another tree's save. */
export type PersistenceIssues = Record<Mothership, PersistenceIssue | null>;

function noIssues(): PersistenceIssues {
  return { research: null, writing: null, reading: null };
}

/** The newest outstanding issue across the trees (null when none). */
function newestIssue(issues: PersistenceIssues): PersistenceIssue | null {
  let newest: PersistenceIssue | null = null;
  for (const issue of Object.values(issues)) {
    if (issue && (newest === null || issue.at >= newest.at)) newest = issue;
  }
  return newest;
}

/** True when the tabs are saved on the server: bound to a project, and the
 *  last save of EVERY tree was accepted (or none has been refused). */
export function tabsSaved(s: Pick<TabTreeState, "tabsPersistence" | "persistenceIssues" | "pendingOps" | "heldClose" | "saving" | "dispatchAllowed" | "loadError" | "loaded" | "trees">): boolean {
  return s.tabsPersistence === "server" && s.dispatchAllowed && s.heldClose === null &&
    Object.values(s.loaded).some(Boolean) &&
    (["reading", "writing", "research"] as const).every((m) => s.trees[m] === null || s.loaded[m]) &&
    Object.values(s.persistenceIssues).every((issue) => issue === null) &&
    Object.values(s.pendingOps).every((ops) => ops.length === 0) &&
    Object.values(s.loadError).every((error) => error === null) &&
    Object.values(s.saving).every((busy) => !busy);
}

/** GET /projects retries after a network error (A2b item 6): three, after
 *  1 s, 4 s and 15 s. */
export const PROJECT_RETRY_DELAYS_MS: readonly number[] = [1_000, 4_000, 15_000];

/** The active project's id, or null when there is none to bind to. May throw
 *  (an ApiError 404 means GET /projects is not deployed). */
export type ActiveProjectSource = (signal?: AbortSignal) => Promise<string | null>;

/** The default source: the first non-archived project GET /projects lists. */
export async function firstOpenProject(signal?: AbortSignal): Promise<string | null> {
  const projects = await listProjects({ signal });
  return projects.find((p) => p.archived_at === null)?.project_id ?? null;
}

/** The HTTP adapter the store binds with: titles come from the tabTitles
 *  cache, the source the strip's labels read. */
function serverAdapter(): TabTreeAdapter {
  return createHttpTabTreeAdapter({ titleOf: (node) => knownTitle(node.kind, node.ref) });
}

function knownTitle(kind: TabNode["kind"], ref: string): string | null {
  const entry = useTabTitles.getState().entries[titleKey(kind, ref)];
  return entry?.state === "known" ? (entry.title ?? "") : null;
}

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
  dispatchAllowed: boolean;
  saving: Record<Mothership, boolean>;
  retrySave: (mothership: Mothership) => void;
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
  /** The project the trees are bound to (null = session, in memory). */
  projectId: string | null;
  tabsPersistence: TabsPersistence;
  /** Per tree: set when that tree's last save was refused, null when it was
   *  accepted (or none has run). The UI copy for it is not written yet; the
   *  state is exposed. */
  persistenceIssues: PersistenceIssues;
  /** Derived from `persistenceIssues`: the newest outstanding issue, null
   *  only when every tree is clean. Kept for callers that want one flag. */
  persistenceIssue: PersistenceIssue | null;

  setTabTreeAdapter: (adapter: TabTreeAdapter) => void;
  /** Bind the trees to the active project (default source: the first
   *  non-archived project). A network error is retried (PROJECT_RETRY_DELAYS_MS)
   *  before giving up. A 404 from GET /projects, a 200 that is not JSON (the
   *  route is absent), no project, or any other failure keeps the in-memory
   *  adapter ("session"). A load waits for a binding in flight, retries
   *  included. */
  bindActiveProject: (
    source?: ActiveProjectSource,
    makeAdapter?: () => TabTreeAdapter,
  ) => Promise<TabsPersistence>;
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

/** The binding in flight (loads wait for it), and whether one has started
 *  (tabTreeHandle.bindOnLoad starts one on the first load). */
let binding: Promise<TabsPersistence> | null = null;
let bindingStarted = false;
/** Serialize adapter saves per mothership (expected-version discipline). */
const saveQueues = new Map<Mothership, Promise<void>>();
/** One in-flight load per mothership (the route sync and a cross-pane open
 *  can both ask on the same tick). */
const loads = new Map<Mothership, Promise<void>>();
const resumeLoads = new Set<Mothership>();
let dispatchController = new AbortController();

function cancelRequests(): void {
  dispatchController.abort();
  dispatchController = new AbortController();
  loads.clear();
  saveQueues.clear();
}
/** Saves asked for while a close was held; run when the hold resolves. */
const deferredSaves = new Set<Mothership>();
let holdTimer: ReturnType<typeof setTimeout> | null = null;
/** The toast offering Undo for each close still undoable, by close_id, so a
 *  keyboard undo takes the toast away with the close. */
const undoToasts = new Map<string, number>();
let navSeq = 0;
/** Written closes still inside their toast's window, by close_id. */
const recentCloses = new Map<string, { mothership: Mothership; token: UndoToken }>();

/** How a failed GET /projects is read. */
type ProjectFailure = "absent" | "network" | "other";

function classifyProjectFailure(e: unknown): ProjectFailure {
  // 404: the route is not deployed.
  if (e instanceof ApiError) {
    const htmlFallback = e.status === 0 && /^\s*(?:<!doctype html|<html)[\s>]/i.test(e.body);
    return e.status === 404 || htmlFallback ? "absent" : "other";
  }
  // A 200 whose body is not JSON: the edge does not route /projects to the
  // API and the SPA fallback answered index.html, so resp.json() threw a
  // SyntaxError. The route is absent exactly as a 404 says it is.
  if (e instanceof SyntaxError) return "absent";
  // fetch rejects (a TypeError) when there is no response at all: the
  // network, not the route. Worth another try.
  return "network";
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) { resolve(); return; }
    const finish = () => { clearTimeout(timer); signal?.removeEventListener("abort", finish); resolve(); };
    const timer = setTimeout(finish, ms);
    signal?.addEventListener("abort", finish, { once: true });
  });
}

/** The active project's id, or null (stay on session). A network error is
 *  retried after each of PROJECT_RETRY_DELAYS_MS; a route that is absent is
 *  not retried and not logged; anything else is logged once. */
type ProjectLookup = { kind: "found"; projectId: string | null } | { kind: "unavailable" };

async function readActiveProject(source: ActiveProjectSource, current: () => boolean, signal: AbortSignal): Promise<ProjectLookup> {
  for (let attempt = 0; ; attempt++) {
    if (!current()) return { kind: "unavailable" };
    try {
      return { kind: "found", projectId: await source(signal) };
    } catch (e) {
      if (!current()) return { kind: "unavailable" };
      const kind = classifyProjectFailure(e);
      if (kind === "absent") return { kind: "unavailable" };
      if (kind === "network" && attempt < PROJECT_RETRY_DELAYS_MS.length) {
        await wait(PROJECT_RETRY_DELAYS_MS[attempt], signal);
        continue;
      }
      // Logged, and the session trees kept rather than lose the operator's tabs.
      // eslint-disable-next-line no-console
      console.error("[antiek/tabs] could not read the active project; tabs stay in this session:", e);
      return { kind: "unavailable" };
    }
  }
}

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
    if (saveQueues.has(mothership)) return;
    const contextEpoch = get().contextEpoch;
    const signal = dispatchController.signal;
    const attempted = new Set<TabOp>();
    const run = Promise.resolve().then(async () => {
      if (get().contextEpoch === contextEpoch && !signal.aborted) await saveNow(mothership, attempted);
    }).finally(() => {
      if (saveQueues.get(mothership) !== run) return;
      saveQueues.delete(mothership);
      // Only a mutation not included in the preceding attempt asks for another
      // write. Duplicate retry clicks cannot multiply a failed CAS sequence.
      if (get().contextEpoch === contextEpoch && !signal.aborted && get().dispatchAllowed &&
        get().pendingOps[mothership].some((op) => !attempted.has(op))) queueSave(mothership);
    });
    saveQueues.set(mothership, run);
  }

  function heldOn(mothership: Mothership): HeldClose | null {
    const held = get().heldClose;
    return held && held.mothership === mothership ? held : null;
  }

  function adapterKey(): string {
    return get().projectId ?? SESSION_PROJECT_KEY;
  }

  function adopt(mothership: Mothership, snapshot: TabTreeSnapshot, ops: TabOp[]): TabTree | null {
    const parsed = fromSnapshot(snapshot);
    if (!parsed.ok) {
      setIssue(mothership, { reason: "unreadable", at: new Date().toISOString(), mothership });
      console.error("[antiek/tabs] unreadable snapshot:", parsed.error.message);
      return null;
    }
    acceptedTrees.set(mothership, parsed.tree);
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
    return rebased;
  }

  async function saveNow(mothership: Mothership, attempted: Set<TabOp>): Promise<void> {
    for (const op of get().pendingOps[mothership]) attempted.add(op);
    if (heldOn(mothership)) {
      deferredSaves.add(mothership);
      return;
    }
    const requestedEpoch = get().contextEpoch;
    const requestedSignal = dispatchController.signal;
    if (!get().dispatchAllowed) return;
    if (binding) await binding;
    if (get().contextEpoch !== requestedEpoch || requestedSignal.aborted) return;
    const { adapter, contextEpoch } = get();
    const signal = dispatchController.signal;
    const current = () => get().contextEpoch === contextEpoch && !signal.aborted;
    const canDispatch = () => current() && get().dispatchAllowed;
    if (!canDispatch()) return;
    if (!get().loaded[mothership]) await get().ensureMothership(mothership);
    if (!canDispatch() || !get().loaded[mothership]) return;
    const key = adapterKey();
    set((state) => ({ saving: { ...state.saving, [mothership]: true } }));
    try {
      let retryTree: TabTree | null = null;
      let retryOps = 0;
      for (let attempt = 0; attempt < 3; attempt++) {
        if (!canDispatch()) return;
        if (!retryTree && heldOn(mothership)) { deferredSaves.add(mothership); return; }
        // Allocate before taking the PUT snapshot. A retry after a lost answer
        // uses the same tab ID; the server registry makes it idempotent.
        const freshIds = new Set(get().pendingOps[mothership].flatMap((op) => op.type === "spawn" ? [op.input.tab_id] : []));
        const candidates = retryTree ? [] : Object.values(get().trees[mothership]?.nodes ?? {}).filter((node) => freshIds.has(node.tab_id));
        // Ordered requests let suspension stop the next POST rather than
        // dispatching every pending tab's allocation at once.
        for (const node of candidates) {
          if (node.public_number !== null) continue;
          if (!canDispatch()) return;
          const number = await adapter.allocate(key, mothership, node.tab_id, signal);
          if (!current()) return;
          const tree = get().trees[mothership];
          if (!tree) return;
          const assigned = assignPublicNumber(tree, node.tab_id, number.public_number);
          if (assigned.ok) set((state) => ({
            trees: { ...state.trees, [mothership]: assigned.tree },
            pendingOps: { ...state.pendingOps, [mothership]: [...state.pendingOps[mothership], assigned.op] },
          }));
          else if (tree.nodes[node.tab_id]) throw new Error(assigned.error.message);
          if (assigned.ok) attempted.add(assigned.op);
        }
        if (!canDispatch()) return;
        if (!retryTree && heldOn(mothership)) { deferredSaves.add(mothership); return; }
        const currentTree = retryTree ?? get().trees[mothership];
        if (!currentTree || get().pendingOps[mothership].length === 0) return;
        const tree = prepareRestores(mothership, currentTree);
        const sentOps = retryTree ? retryOps : get().pendingOps[mothership].length;
        for (const op of get().pendingOps[mothership].slice(0, sentOps)) attempted.add(op);
        const result = await adapter.save(key, mothership, toSnapshot(tree), signal);
        if (!current()) return;
        if (result.status === "saved") {
          const remaining = get().pendingOps[mothership].slice(sentOps);
          const focused = get().trees[mothership]?.active_tab_id;
          const adopted = adopt(mothership, result.snapshot, remaining);
          if (adopted) {
            if (focused && adopted.nodes[focused]) set((state) => {
              const shown = state.trees[mothership];
              return current() && shown?.nodes[focused]
                ? { trees: { ...state.trees, [mothership]: { ...shown, active_tab_id: focused } } }
                : state;
            });
            setIssue(mothership, null);
          }
          return;
        }
        if (result.status === "conflict") {
          retryTree = adopt(mothership, result.current, get().pendingOps[mothership]);
          retryOps = get().pendingOps[mothership].length;
          if (!retryTree) return;
          if (attempt === 2) {
            setIssue(mothership, { reason: "conflict", at: new Date().toISOString(), mothership });
            return;
          }
          if (attempt > 0) await wait(100, signal);
          continue;
        }
        reportInvalid(mothership, result);
        if (!canDispatch()) return;
        const fresh = await adapter.load(key, mothership, signal);
        if (current()) adopt(mothership, fresh, get().pendingOps[mothership]);
        return;
      }
    } catch (error) {
      if (!current()) return;
      setIssue(mothership, { reason: "transport", at: new Date().toISOString(), mothership });
      console.error("[antiek/tabs] save failed; pending changes retained:", error);
    } finally {
      if (current()) set((state) => ({ saving: { ...state.saving, [mothership]: false } }));
    }
  }

  /** A 422: log it (a lane-A bug) and record that the tabs are not saved. */
  function reportInvalid(mothership: Mothership, result: { reason: string; tab_id: string | null; detail: string }): void {
    // eslint-disable-next-line no-console
    console.error(
      `[antiek/tabs] the server refused the tab snapshot (${result.reason}${result.tab_id ? `, tab ${result.tab_id}` : ""}), a lane-A bug: ${result.detail}`,
    );
    setIssue(mothership, { reason: "refused", at: new Date().toISOString(), mothership });
  }

  function setIssue(mothership: Mothership, issue: PersistenceIssue | null): void {
    const persistenceIssues = { ...get().persistenceIssues, [mothership]: issue };
    set({ persistenceIssues, persistenceIssue: newestIssue(persistenceIssues) });
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
    dispatchAllowed: !getTabOwner().suspended,
    saving: emptyLoaded(),
    retrySave: queueSave,
    trees: { research: null, writing: null, reading: null },
    loaded: emptyLoaded(),
    loadError: noErrors(),
    pendingOps: { research: [], writing: [], reading: [] },
    treePanelOpen: false,
    subtreeFocusId: null,
    heldClose: null,
    navIntent: null,
    adapter: createInMemoryTabTreeAdapter(),
    projectId: null,
    tabsPersistence: "session",
    persistenceIssues: noIssues(),
    persistenceIssue: null,

    setTabTreeAdapter: (adapter) => {
      cancelRequests();
      resumeLoads.clear();
      acceptedTrees.clear();
      saveQueues.clear();
      deferredSaves.clear();
      recentCloses.clear();
      for (const id of undoToasts.values()) toast.dismiss(id);
      undoToasts.clear();
      if (holdTimer !== null) clearTimeout(holdTimer);
      holdTimer = null;
      // An explicit adapter is its own binding: no project detection runs.
      bindingStarted = true;
      binding = null;
      set({
        heldClose: null,
        navIntent: null,
        contextEpoch: get().contextEpoch + 1,
        saving: emptyLoaded(),
        dispatchAllowed: (!tabTreeHandle.bindOnLoad || getTabOwner().owner !== null) && !getTabOwner().suspended,
        adapter,
        projectId: null,
        tabsPersistence: "session",
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
        persistenceIssues: noIssues(),
        persistenceIssue: null,
      });
    },

    bindActiveProject: (source = firstOpenProject, makeAdapter = serverAdapter) => {
      if (binding) return binding;
      const epoch = get().contextEpoch;
      const owner = getTabOwner();
      const signal = dispatchController.signal;
      if (!owner.owner || owner.suspended) return Promise.resolve(get().tabsPersistence);
      bindingStarted = true;
      const run = (async (): Promise<TabsPersistence> => {
        const lookup = await readActiveProject(source, () => get().contextEpoch === epoch && !signal.aborted && !getTabOwner().suspended, signal);
        if (get().contextEpoch !== epoch || signal.aborted || getTabOwner().suspended) return get().tabsPersistence;
        if (lookup.kind === "unavailable") return get().tabsPersistence;
        const { projectId } = lookup;
        if (projectId === null) {
          if (get().projectId !== null) {
            get().resetTabTrees();
            bindingStarted = true;
          }
          set({ tabsPersistence: "session", projectId: null });
          return "session";
        }
        const switchingProject = get().projectId !== null && get().projectId !== projectId;
        const adapter = makeAdapter();
        if (switchingProject) get().resetTabTrees();
        else cancelRequests();
        acceptedTrees.clear();
        bindingStarted = true;
        set({
          adapter,
          projectId,
          tabsPersistence: "server",
          persistenceIssues: noIssues(),
          persistenceIssue: null,
          loaded: emptyLoaded(),
          loadError: noErrors(),
        });
        for (const mothership of ["reading", "writing", "research"] as const) {
          if (get().pendingOps[mothership].length) queueSave(mothership);
        }
        return "server";
      })();
      binding = run;
      void run.finally(() => {
        if (binding === run) binding = null;
      });
      return run;
    },

    ensureMothership: (mothership) => {
      if (get().loaded[mothership]) return Promise.resolve();
      const inflight = loads.get(mothership);
      if (inflight) return inflight;
      if (!bindingStarted && tabTreeHandle.bindOnLoad) void get().bindActiveProject();
      const requestedEpoch = get().contextEpoch;
      const requestedOwnerEpoch = getTabOwner().epoch;
      let run: Promise<void> | null = null;
      run = (async () => {
        const waitingForBinding = binding;
        if (waitingForBinding) await waitingForBinding;
        if (waitingForBinding && getTabOwner().epoch === requestedOwnerEpoch && get().projectId !== null && loads.get(mothership) !== run) {
          await get().ensureMothership(mothership);
          return;
        }
        if (get().contextEpoch !== requestedEpoch) {
          if (waitingForBinding && getTabOwner().epoch === requestedOwnerEpoch && get().projectId !== null) {
            await get().ensureMothership(mothership);
          }
          return;
        }
        const { adapter, contextEpoch } = get();
        const signal = dispatchController.signal;
        if (get().tabsPersistence === "server" && !get().dispatchAllowed) return;
        try {
          const snapshot = await adapter.load(adapterKey(), mothership, signal);
          if (get().contextEpoch !== contextEpoch || signal.aborted) return;
          const parsed = fromSnapshot(snapshot);
          if (!parsed.ok) {
            // Never start from an empty tree here: its first save would close
            // every tab the server holds.
            throw new Error(`the saved tabs are unreadable: ${parsed.error.message}`);
          }
          // Ops made before the load landed replay on the loaded tree.
          const pending = get().pendingOps[mothership] ?? [];
          const tree = adopt(mothership, snapshot, pending);
          if (!tree) throw new Error("the saved tabs are unreadable");
          set((s) => ({
            loaded: { ...s.loaded, [mothership]: true },
            loadError: { ...s.loadError, [mothership]: null },
          }));
          if (get().pendingOps[mothership].length) queueSave(mothership);
        } catch (e) {
          if (get().contextEpoch !== contextEpoch || signal.aborted) return;
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
      const title = input.title ?? knownTitle(input.kind, input.ref) ?? undefined;
      const result = spawnChild(tree, parentId, title === undefined ? input : { ...input, title });
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
      cancelRequests();
      resumeLoads.clear();
      binding = null;
      bindingStarted = false;
      deferredSaves.clear();
      recentCloses.clear();
      undoToasts.clear();
      saveQueues.clear();
      resetTabTitles();
      acceptedTrees.clear();
      set({
        contextEpoch: get().contextEpoch + 1,
        saving: emptyLoaded(),
        dispatchAllowed: (!tabTreeHandle.bindOnLoad || getTabOwner().owner !== null) && !getTabOwner().suspended,
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
        treePanelOpen: false,
        subtreeFocusId: null,
        heldClose: null,
        navIntent: null,
        adapter: createInMemoryTabTreeAdapter(),
        projectId: null,
        tabsPersistence: "session",
        persistenceIssues: noIssues(),
        persistenceIssue: null,
      });
    },
  };
});

// The keyboard dispatcher (entry chunk) reaches the store through this
// handle; the store itself loads with the lazy strip.
tabTreeHandle.store = useTabTrees;

let ownerEpoch = getTabOwner().epoch;
subscribeTabOwner(() => {
  const owner = getTabOwner();
  if (owner.epoch !== ownerEpoch) {
    ownerEpoch = owner.epoch;
    useTabTrees.getState().resetTabTrees();
  }
  const allowed = owner.owner !== null && !owner.suspended;
  if (!allowed && useTabTrees.getState().dispatchAllowed) {
    for (const mothership of loads.keys()) resumeLoads.add(mothership);
    cancelRequests();
    if (binding) {
      binding = null;
      bindingStarted = false;
    }
    useTabTrees.setState((state) => ({
      saving: emptyLoaded(),
      ...(state.tabsPersistence === "server" ? { loaded: emptyLoaded() } : {}),
    }));
  }
  useTabTrees.setState({ dispatchAllowed: allowed });
  if (allowed) {
    const state = useTabTrees.getState();
    if (tabTreeHandle.bindOnLoad && !bindingStarted) void state.bindActiveProject();
    for (const mothership of ["reading", "writing", "research"] as const) {
      if (resumeLoads.delete(mothership) || (state.tabsPersistence === "server" && state.trees[mothership])) void state.ensureMothership(mothership);
      if (state.pendingOps[mothership].length) state.retrySave(mothership);
    }
  }
});
