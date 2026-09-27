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
import { ApiError } from "../lib/api";
import { listProjects } from "../lib/api/projects";
import { labelForTab } from "./tabLabels";
import { resetTabTitles, titleKey, useTabTitles } from "./tabTitles";
import { tabTreeHandle } from "./tabTreeHandle";
import {
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
import { createHttpTabTreeAdapter } from "./tabTreeHttpAdapter";

/** The key the in-memory adapter files session trees under. It never
 *  reaches a server: a server-bound store uses the active project's id. */
export const SESSION_PROJECT_KEY = "default";

/** Where the trees are saved to: "session" (in memory, gone on reload) or
 *  "server" (the active project's row, §1.6). It claims the tabs ARE saved
 *  only while no tree has a `persistenceIssues` entry: see `tabsSaved`. */
export type TabsPersistence = "session" | "server";

/** The last save of `mothership`'s tree was refused (a 422: Part 2 §2.2
 *  calls it a lane-A bug). The store has already logged it, refetched and
 *  rebased, so the tabs are on screen but not saved. A later accepted save of
 *  that tree clears it. `at` is when the refusal came back (ISO 8601). */
export interface PersistenceIssue {
  reason: "refused";
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
export function tabsSaved(s: { tabsPersistence: TabsPersistence; persistenceIssues: PersistenceIssues }): boolean {
  return s.tabsPersistence === "server" && Object.values(s.persistenceIssues).every((issue) => issue === null);
}

/** GET /projects retries after a network error (A2b item 6): three, after
 *  1 s, 4 s and 15 s. */
export const PROJECT_RETRY_DELAYS_MS: readonly number[] = [1_000, 4_000, 15_000];

/** The active project's id, or null when there is none to bind to. May throw
 *  (an ApiError 404 means GET /projects is not deployed). */
export type ActiveProjectSource = () => Promise<string | null>;

/** The default source: the first non-archived project GET /projects lists. */
export async function firstOpenProject(): Promise<string | null> {
  const projects = await listProjects();
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
  if (e instanceof ApiError) return e.status === 404 ? "absent" : "other";
  // A 200 whose body is not JSON: the edge does not route /projects to the
  // API and the SPA fallback answered index.html, so resp.json() threw a
  // SyntaxError. The route is absent exactly as a 404 says it is.
  if (e instanceof SyntaxError) return "absent";
  // fetch rejects (a TypeError) when there is no response at all: the
  // network, not the route. Worth another try.
  return "network";
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** The active project's id, or null (stay on session). A network error is
 *  retried after each of PROJECT_RETRY_DELAYS_MS; a route that is absent is
 *  not retried and not logged; anything else is logged once. */
async function readActiveProject(source: ActiveProjectSource): Promise<string | null> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await source();
    } catch (e) {
      const kind = classifyProjectFailure(e);
      if (kind === "absent") return null;
      if (kind === "network" && attempt < PROJECT_RETRY_DELAYS_MS.length) {
        await wait(PROJECT_RETRY_DELAYS_MS[attempt]);
        continue;
      }
      // Logged, and the session trees kept rather than lose the operator's tabs.
      // eslint-disable-next-line no-console
      console.error("[antiek/tabs] could not read the active project; tabs stay in this session:", e);
      return null;
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
    const run = prior.then(() => saveNow(mothership));
    saveQueues.set(mothership, run);
  }

  function heldOn(mothership: Mothership): HeldClose | null {
    const held = get().heldClose;
    return held && held.mothership === mothership ? held : null;
  }

  function adapterKey(): string {
    return get().projectId ?? SESSION_PROJECT_KEY;
  }

  /**
   * Make the server's snapshot the base and replay `replay` (the ops it has
   * not seen) on top: after a saved PUT (its numbers, version and retired
   * rows win), after a 409 (`current`) and after a 422's refetch. A close
   * still inside its undo window is replayed for the screen only, never into
   * the pending log. Returns the rebased tree WITHOUT the held close (what
   * the next PUT may write), or null when the snapshot is unreadable.
   */
  function adopt(mothership: Mothership, snapshot: TabTreeSnapshot, replay: TabOp[]): TabTree | null {
    const parsed = fromSnapshot(snapshot);
    if (!parsed.ok) {
      // eslint-disable-next-line no-console
      console.error("[antiek/tabs] the server's snapshot is unreadable:", parsed.error.message);
      return null;
    }
    const { tree: rebased, dropped } = rebase(parsed.tree, replay);
    if (dropped.length > 0) {
      toast.info("A tab was closed on another device; your other changes were kept.");
    }
    const held = heldOn(mothership);
    let shown = rebased;
    if (held && held.op.type === "close") {
      const op = held.op;
      const again = closeTab(rebased, op.tab_id, op.mode, op.now, op.close_id);
      if (again.ok) {
        shown = again.tree;
        set({ heldClose: { mothership, token: again.undo, op: again.op } });
      } else {
        // Another device already closed it: nothing is left to hold.
        if (holdTimer !== null) clearTimeout(holdTimer);
        holdTimer = null;
        set({ heldClose: null });
      }
    }
    set((s) => ({
      trees: { ...s.trees, [mothership]: shown },
      pendingOps: { ...s.pendingOps, [mothership]: replay },
    }));
    return rebased;
  }

  /** A saved answer: the ops made while the save was in flight (after the
   *  first `sentOps`) replay on the server's snapshot and stay pending. */
  function adoptSaved(mothership: Mothership, snapshot: TabTreeSnapshot, sentOps: number): void {
    const inFlight = (get().pendingOps[mothership] ?? []).slice(sentOps);
    // Accepted: whatever an earlier refusal of THIS tree said no longer holds.
    // Another tree's refusal is its own slot and stays.
    if (get().persistenceIssues[mothership] !== null) setIssue(mothership, null);
    adopt(mothership, snapshot, inFlight);
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
    const { adapter, trees, pendingOps } = get();
    const tree = trees[mothership];
    if (!tree) return;
    const key = adapterKey();
    const sentOps = (pendingOps[mothership] ?? []).length;
    let result;
    try {
      result = await adapter.save(key, mothership, toSnapshot(tree));
    } catch (e) {
      // A transport failure: nothing was accepted, so every op stays pending
      // and the next write carries it. Never a user-facing error.
      // eslint-disable-next-line no-console
      console.error("[antiek/tabs] save failed; retrying with the next write:", e);
      return;
    }
    if (get().adapter !== adapter) return; // rebound mid-flight
    if (result.status === "saved") {
      adoptSaved(mothership, result.snapshot, sentOps);
      return;
    }
    if (result.status === "conflict") {
      // Another writer won (version_stale), or another device's accepted
      // spawn moved a counter past a pending number (number_conflict). Both
      // rebase the same way, silently: every op made so far, including those
      // made while the save was in flight, replays on `current` (spawns are
      // never lost; dead ops drop with one quiet toast), and the tree is
      // saved once more. A close held while the save was in flight stays
      // held: replayed for the screen only (same close_id, so its toast's
      // Undo still finds it); the retry writes the tree WITHOUT it.
      const ops = get().pendingOps[mothership] ?? [];
      const rebased = adopt(mothership, result.current, ops);
      if (rebased === null) return;
      const retrySent = ops.length;
      try {
        const retry = await adapter.save(key, mothership, toSnapshot(rebased));
        if (get().adapter !== adapter) return;
        if (retry.status === "saved") adoptSaved(mothership, retry.snapshot, retrySent);
        else if (retry.status === "conflict") adopt(mothership, retry.current, get().pendingOps[mothership] ?? []);
        else reportInvalid(mothership, retry);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[antiek/tabs] save failed; retrying with the next write:", e);
      }
      // The hold may have ended while the rebase was in flight.
      if (!heldOn(mothership)) flushDeferred();
      return;
    }
    // A 422: the server refused the snapshot. Part 2 §2.2: a lane-A bug. Log
    // it with its detail, refetch and rebase; never show it to the operator.
    reportInvalid(mothership, result);
    try {
      const fresh = await adapter.load(key, mothership);
      if (get().adapter !== adapter) return;
      adopt(mothership, fresh, get().pendingOps[mothership] ?? []);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("[antiek/tabs] refetch after a refused save failed:", e);
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
    recentCloses.set(closeId, { mothership: held.mothership, token: held.token });
    setTimeout(() => {
      recentCloses.delete(closeId);
      undoToasts.delete(closeId);
    }, UNDO_TTL_MS);
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
    navIntent: null,
    adapter: createInMemoryTabTreeAdapter(),
    projectId: null,
    tabsPersistence: "session",
    persistenceIssues: noIssues(),
    persistenceIssue: null,

    setTabTreeAdapter: (adapter) => {
      loads.clear();
      // An explicit adapter is its own binding: no project detection runs.
      bindingStarted = true;
      binding = null;
      set({
        adapter,
        trees: { research: null, writing: null, reading: null },
        loaded: emptyLoaded(),
        loadError: noErrors(),
        pendingOps: { research: [], writing: [], reading: [] },
        persistenceIssues: noIssues(),
        persistenceIssue: null,
      });
    },

    bindActiveProject: (source = firstOpenProject, makeAdapter = serverAdapter) => {
      bindingStarted = true;
      const run = (async (): Promise<TabsPersistence> => {
        const projectId = await readActiveProject(source);
        if (projectId === null) {
          set({ tabsPersistence: "session", projectId: null });
          return "session";
        }
        loads.clear();
        saveQueues.clear();
        set({
          adapter: makeAdapter(),
          projectId,
          tabsPersistence: "server",
          persistenceIssues: noIssues(),
          persistenceIssue: null,
          trees: { research: null, writing: null, reading: null },
          loaded: emptyLoaded(),
          loadError: noErrors(),
          pendingOps: { research: [], writing: [], reading: [] },
        });
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
      let run: Promise<void> | null = null;
      run = (async () => {
        if (binding) await binding;
        const adapter = get().adapter;
        try {
          const snapshot = await adapter.load(adapterKey(), mothership);
          if (get().adapter !== adapter) return; // swapped mid-flight
          const parsed = fromSnapshot(snapshot);
          if (!parsed.ok) {
            // Never start from an empty tree here: its first save would close
            // every tab the server holds.
            throw new Error(`the saved tabs are unreadable: ${parsed.error.message}`);
          }
          // Ops made before the load landed replay on the loaded tree.
          const pending = get().pendingOps[mothership] ?? [];
          const tree = pending.length > 0 ? rebase(parsed.tree, pending).tree : parsed.tree;
          set((s) => ({
            trees: { ...s.trees, [mothership]: tree },
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
        heldClose: { mothership, token: result.undo, op: result.op },
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
      const result = undo(tree, recent.token);
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
      binding = null;
      bindingStarted = false;
      deferredSaves.clear();
      recentCloses.clear();
      undoToasts.clear();
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
