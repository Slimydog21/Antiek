/**
 * Branch tab tree: the pure model (MS-04 milestone 1).
 *
 * TAB ≠ BRANCH. This file is NAVIGATION state: which tabs are open, how they
 * nest, and the numbers that address them. A research BRANCH is PROVENANCE:
 * a durable parent → child dependency written into the parent
 * investigation's log before the child starts (THREAD-CONTRACT §1.3 and
 * Part 2 §2.2 "Tab ≠ branch"). They are separate records on purpose. Pruning
 * or closing a tab must never delete, rewrite or "clean up" a branch; the
 * companion document's "how I got here" reads the branch record, not this
 * tree. The regression test that pins this is MS-04 M7's "a pruned research
 * tab's investigation is untouched". This module has no I/O, so it cannot
 * reach a branch at all.
 *
 * Binding spec: THREAD-CONTRACT.md rev 2 §1.6 (storage and addressing) and
 * Part 2 §2.2 (Tab; rev 7 adds `side` and the `agent` origin with
 * `opened_by`, both here; right-side agent nodes and `active: {left, right}`
 * are staged until lane B's adapter, see README "§2.2 rev 7"); DESIGN-MODEL.md
 * §2a; DECISIONS.md D6 (sub-branches are "infinitely layered"). Invariants
 * I1–I9 are enumerated at the top of tabTree.property.test.ts.
 *
 * Rules this model keeps:
 *  - Pure. Every operation returns a new tree and never mutates its input.
 *    Bad input is an error result, never a throw.
 *  - Numbers are addresses. hier_number is `<parent's hier_number>.<n>` at
 *    spawn, with n from a per-parent monotonic counter (root included). It is
 *    never reused and never renumbered; lift keeps it. The one exception is a
 *    pending spawn recomputed by `rebase`: a number is final only once the
 *    snapshot carrying it is accepted (contract R3-5).
 *  - public_number is never invented here. It starts null (Part 2's
 *    `numbering` state) and is set only by `assignPublicNumber` with a value
 *    from the server's allocate route.
 *  - Close is soft. Closed tabs move to `history` with their numbers, so undo
 *    and history links stay stable. Reuse means a DIFFERENT tab_id taking a
 *    number; the same tab_id restored is not reuse (contract R3-1).
 *  - `history` is the client's view of the server's `retired[]` (§1.6 rev 7):
 *    each entry is `{node, closed_at, close_mode}` plus a client-only
 *    `close_id`. `pruned_at` is the SERVER's: it is set on a retired node
 *    that left by prune, never by this model, and a restore puts the node
 *    back unchanged, `pruned_at` included, for the server to clear (rev 8.8).
 *  - Every node has a `side` (§1.6 rev 7). A child inherits its parent's
 *    side, except `agent` and `derivation` children, which are always left
 *    (Part 2 §2.2). Every spawn this client makes today is left.
 *  - Every traversal is iterative, so depth is bounded by memory, not by the
 *    call stack.
 *  - Tab state never goes to localStorage or sessionStorage (§1.6).
 *    Persistence goes through `TabTreeAdapter`; the in-memory adapter below
 *    stands in for lane B's GET/PUT/allocate routes until W1 ships.
 */

// ---------------------------------------------------------------------------
// Types (contract names)
// ---------------------------------------------------------------------------

export type Mothership = "research" | "writing" | "reading";

/** Branch kinds as the UI names them. `agent` is a document an agent tab
 *  opened (it needs `opened_by`); `derivation` is a reformat result (§1.6
 *  rev 7/8). Both are navigation state only and write no branch. */
export type BranchKind =
  | "footnote"
  | "reference"
  | "citation"
  | "island"
  | "research"
  | "manual"
  | "agent"
  | "derivation";

/** Branch kinds on the wire. "island" is never a backend or event name
 *  (contract §1.0, R2-1): payloads say "selection". */
export type WireBranchKind =
  | "footnote"
  | "reference"
  | "citation"
  | "selection"
  | "research"
  | "manual"
  | "agent"
  | "derivation";

/** Left nodes are document tabs (the core material); right nodes are agent
 *  tabs, each a view of one thread, plus the Findings tab (§1.6 rev 7). */
export type TabSide = "left" | "right";

/** Kinds by side (§1.6 rev 8.8). `research` is on both sides: on the left a
 *  deep research spawned from a document, on the right a research as an
 *  agent. This client spawns only left kinds today; the right kinds are here
 *  so a tree read from the server holds its right nodes unchanged (A14 moves
 *  the agent tabs into the tree). */
export type LeftTabKind = "reader" | "document" | "research";
export type RightTabKind =
  | "research"
  | "dialogue"
  | "reformat"
  | "diligence"
  | "island"
  | "findings"
  | "flags"
  | "block";
export type TabKind = LeftTabKind | RightTabKind;

const KINDS_BY_SIDE: Readonly<Record<TabSide, ReadonlySet<string>>> = {
  left: new Set<LeftTabKind>(["reader", "document", "research"]),
  right: new Set<RightTabKind>(["research", "dialogue", "reformat", "diligence", "island", "findings", "flags", "block"]),
};

/** True when `kind` is admitted on `side` (§1.6 rev 8.8). */
export function kindAllowedOnSide(kind: string, side: TabSide): boolean {
  return KINDS_BY_SIDE[side]?.has(kind) ?? false;
}

/** The `TextLocator` shape (contract §1.4). */
export interface TextLocator {
  start: number;
  end: number;
  text_sha256: string;
  block_id?: string;
}

/** Contract §1.4. `source_locator` is the durable key. */
export interface BranchAnchor {
  document_id: string;
  source_locator?: TextLocator;
  region_id?: string;
  anchor_id?: string;
  quote?: string;
  prefix?: string;
  suffix?: string;
  page_index?: number;
}

/** Who opened an `agent`-origin tab (§1.6 rev 7, S1). Required for `agent`. */
export interface OpenedBy {
  thread_id: string;
  agent_kind: string;
}

/** What the tab's pane has docked (Part 2 §2.2 Needs). */
export interface PaneDock {
  docked_kind?: string;
  docked_ref?: string;
}

export interface BranchOrigin<K extends string = BranchKind> {
  document_id: string;
  anchor?: BranchAnchor;
  kind: K;
}

/** A node in the tab tree (contract Part 2 §2.2). */
export interface TabNode<K extends string = BranchKind> {
  tab_id: string;
  parent_tab_id: string | null;
  side: TabSide;
  branch_origin?: BranchOrigin<K>;
  /** Required when branch_origin.kind is `agent`. */
  opened_by?: OpenedBy;
  hier_number: string;
  child_order: readonly string[];
  last_visited_child_id?: string;
  /** The server's, on a retired node that left by prune. An open node carries
   *  it only between a restore and the server accepting it (rev 8.8). */
  pruned_at?: string;
  kind: TabKind;
  ref: string;
  /** Derived from the ref (§2.2); empty until the surface names it. */
  title: string;
  mothership: Mothership;
  pane?: PaneDock;
  public_number: number | null;
}

/** How a close is asked for (the operation). */
export type CloseMode = "prune" | "lift_children";

/** How the server records a retirement, read off the diff (§1.6):
 *  `lift_children` when a child of the dropped tab stays, `prune` when it
 *  took children with it or went with a pruned parent, otherwise `close`. */
export type RetireMode = "close" | "prune" | "lift_children";

/** A closed tab: one of the server's `retired[]` entries, or a local close
 *  not yet written. `node` is the tab exactly as it left the tree;
 *  `close_id` (client-only) names the close that put it here, so an undo
 *  token can prove it is undoing that close and not a later one. */
export interface ClosedTab<K extends string = BranchKind> {
  node: TabNode<K>;
  close_id: string;
  closed_at: string;
  close_mode: RetireMode;
}

export interface TabTree {
  mothership: Mothership;
  /** Open tabs by tab_id. */
  nodes: Readonly<Record<string, TabNode>>;
  root_order: readonly string[];
  /** The focused tab. On the wire it is `active.left` when it is a left tab. */
  active_tab_id: string | null;
  /** The server's `active.right`, held unchanged until agent tabs move into
   *  the tree (A14); cleared when that tab closes. */
  active_right: string | null;
  active_left: string | null;
  /** Closed and pruned tabs by tab_id (soft close: recoverable, numbers kept). */
  history: Readonly<Record<string, ClosedTab>>;
  /** Retired-node proof for restores awaiting server acknowledgment; never serialized. */
  restoring?: Readonly<Record<string, TabNode>>;
  /** Next index for a root tab. Monotonic. */
  next_root_index: number;
  /** Next child index per parent tab_id (absent = 1). Monotonic. */
  next_child_index: Readonly<Record<string, number>>;
  /** The server version this tree descends from: the `expected_version` of
   *  the next PUT. Local operations never change it; `rebase` takes the
   *  remote's, and `withVersion` records a successful save. */
  version: number;
}

export type TabTreeErrorCode =
  | "invalid_tab_id"
  | "duplicate_tab_id"
  | "wrong_mothership"
  | "tab_not_open"
  | "unknown_tab"
  | "public_number_invalid"
  | "public_number_taken"
  | "already_numbered"
  | "not_closed_by_token"
  | "no_children"
  | "invalid_snapshot"
  | "tab_origin_invalid"
  | "kind_side_mismatch";

export interface TabTreeError {
  code: TabTreeErrorCode;
  message: string;
}

export type TabTreeResult<T> = ({ ok: true } & T) | { ok: false; error: TabTreeError };

export interface SpawnInput {
  tab_id: string;
  origin?: BranchOrigin;
  kind: TabKind;
  ref: string;
  mothership: Mothership;
  /** The tab's title, when the surface already knows it. Default "". */
  title?: string;
  /** A ROOT's side (default left). A child's side is derived: its parent's,
   *  or left for an `agent` or `derivation` origin. */
  side?: TabSide;
  /** Required for an `agent` origin. */
  opened_by?: OpenedBy;
  pane?: PaneDock;
  /** Focus the new tab. Default true; false for a background spawn, such as
   *  an agent's autonomous branch, which must not steal focus. */
  activate?: boolean;
}

/** Everything `undo` needs to put one close back. It is plain data, so it can
 *  ride in the op log and survive a rebase. */
export interface UndoToken {
  close_id: string;
  mode: CloseMode;
  tab_id: string;
  /** The closed tab's parent at close time (null = it was a root). */
  parent_tab_id: string | null;
  /** Its position among its siblings at close time, and its neighbours. */
  index: number;
  prev_sibling_id: string | null;
  next_sibling_id: string | null;
  prev_active_tab_id: string | null;
  /** The right pane's active tab at close time (absent on older tokens). */
  prev_active_right?: string | null;
  prev_active_left?: string | null;
  /** The parent's last_visited_child_id pointed at the closed tab. */
  parent_remembered_it: boolean;
}

/** The op log. Every operation returns the op it applied so a caller can keep
 *  the pending log that `rebase` replays after a 409. */
export type TabOp =
  | { type: "spawn"; parent_tab_id: string | null; input: SpawnInput; hier_number: string }
  | { type: "close"; close_id: string; tab_id: string; mode: CloseMode; now: string; seen_tab_ids: readonly string[] }
  | { type: "undo"; token: UndoToken; restore_retired?: boolean }
  | { type: "restore"; tab_id: string; close_id: string }
  | { type: "assign_public_number"; tab_id: string; public_number: number }
  | { type: "set_active"; tab_id: string | null };

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function fail(code: TabTreeErrorCode, message: string): { ok: false; error: TabTreeError } {
  return { ok: false, error: { code, message } };
}

/** Own-property lookups only: a tab_id such as "constructor" must not find
 *  Object.prototype. */
function openNode(tree: TabTree, id: string): TabNode | undefined {
  return Object.hasOwn(tree.nodes, id) ? tree.nodes[id] : undefined;
}

function closedTab(tree: TabTree, id: string): ClosedTab | undefined {
  return Object.hasOwn(tree.history, id) ? tree.history[id] : undefined;
}

function isKnown(tree: TabTree, id: string): boolean {
  return Object.hasOwn(tree.nodes, id) || Object.hasOwn(tree.history, id);
}

/** THREAD-CONTRACT §1.6: a tab_id is 1 to 64 of [A-Za-z0-9_-]. */
const TAB_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

/** True when `id` is a tab_id the server accepts and a record can key. */
export function isLegalTabId(id: unknown): id is string {
  return typeof id === "string" && TAB_ID_RE.test(id) && id !== "__proto__" && id !== "root";
}

/** tab_ids are record keys. "__proto__" is the one key a plain object cannot
 *  hold safely, so it is refused. */
function tabIdProblem(id: unknown): string | null {
  if (typeof id !== "string" || id.length === 0) return "tab_id must be a non-empty string";
  if (id === "root") return 'tab_id "root" is reserved for root counters';
  if (id === "__proto__") return 'tab_id "__proto__" is reserved';
  if (!TAB_ID_RE.test(id)) return `tab_id ${JSON.stringify(id)} is not 1 to 64 of [A-Za-z0-9_-]`;
  return null;
}

function siblingsOf(tree: TabTree, parentId: string | null): readonly string[] {
  return parentId === null ? tree.root_order : (openNode(tree, parentId)?.child_order ?? []);
}

function withoutLastVisited(node: TabNode): TabNode {
  const copy = { ...node };
  delete copy.last_visited_child_id;
  return copy;
}

/** The index the next child of `parentId` (null = root) gets. Monotonic:
 *  closing a child never frees its index (I4). */
function nextIndex(tree: TabTree, parentId: string | null): number {
  if (parentId === null) return tree.next_root_index;
  return Object.hasOwn(tree.next_child_index, parentId) ? tree.next_child_index[parentId] : 1;
}

/** Make `id` active and point every ancestor's last_visited_child_id down the
 *  path to it, so `prefix+o` from any ancestor retraces the way back down.
 *  `owned` is a nodes record the caller just built and may still write, which
 *  saves a second O(tabs) copy on spawn. */
function activate(tree: TabTree, id: string | null, owned?: Record<string, TabNode>): TabTree {
  if (id === null) return tree.active_tab_id === null ? tree : { ...tree, active_tab_id: null };
  let nodes: Record<string, TabNode> | null = owned ?? null;
  let child = id;
  let parentId = tree.nodes[id].parent_tab_id;
  while (parentId !== null) {
    const parent = (nodes ?? tree.nodes)[parentId];
    if (parent.last_visited_child_id !== child) {
      nodes ??= { ...tree.nodes };
      nodes[parentId] = { ...parent, last_visited_child_id: child };
    }
    child = parentId;
    parentId = parent.parent_tab_id;
  }
  if (nodes === null && tree.active_tab_id === id) return tree;
  return { ...tree, nodes: nodes ?? tree.nodes, active_tab_id: id,
    ...(tree.nodes[id].side === "left" ? { active_left: id } : { active_right: id }) };
}

// ---------------------------------------------------------------------------
// Kind mapping (contract §1.0)
// ---------------------------------------------------------------------------

export function toWireKind(kind: BranchKind): WireBranchKind {
  return kind === "island" ? "selection" : kind;
}

export function fromWireKind(kind: WireBranchKind): BranchKind {
  return kind === "selection" ? "island" : kind;
}

const WIRE_KINDS: ReadonlySet<string> = new Set(["footnote", "reference", "citation", "selection", "research", "manual", "agent", "derivation"]);

/** An `agent` origin must name who opened it, and only an agent origin may
 *  (§2.2 S1). Null = valid. */
function originProblem(kind: string | undefined, openedBy: OpenedBy | undefined): string | null {
  const named = !!openedBy && typeof openedBy.thread_id === "string" && openedBy.thread_id.trim() !== ""
    && typeof openedBy.agent_kind === "string" && openedBy.agent_kind.trim() !== "";
  if (kind === "agent" && !named) return "an agent-opened tab needs opened_by {thread_id, agent_kind}";
  if (kind !== "agent" && openedBy !== undefined) return "opened_by is only for an agent-opened tab";
  return null;
}

// ---------------------------------------------------------------------------
// Construction and queries
// ---------------------------------------------------------------------------

export function emptyTabTree(mothership: Mothership, version = 0): TabTree {
  return {
    mothership,
    nodes: {},
    root_order: [],
    active_tab_id: null,
    active_right: null,
    active_left: null,
    history: {},
    next_root_index: 1,
    next_child_index: {},
    version,
  };
}

/** Record a successful PUT: the tree now descends from `version`. */
export function withVersion(tree: TabTree, version: number): TabTree {
  return { ...tree, version };
}

/** A successful PUT acknowledges only the restore records that request carried. */
export function acknowledgeRestores(tree: TabTree, sent: TabTree, version: number): TabTree {
  const nodes = { ...tree.nodes };
  const restoring = { ...tree.restoring };
  for (const id of Object.keys(sent.restoring ?? {})) {
    if (restoring[id] !== sent.restoring?.[id]) continue;
    if (nodes[id]?.pruned_at === restoring[id].pruned_at) nodes[id] = withoutPrunedAt(nodes[id]);
    delete restoring[id];
  }
  const next = { ...tree, nodes, version };
  if (Object.keys(restoring).length > 0) next.restoring = restoring;
  else delete next.restoring;
  return next;
}

/** Root → tab, as tab_ids. Empty when the tab is not open. Iterative. */
export function pathTo(tree: TabTree, tabId: string): string[] {
  const path: string[] = [];
  let cur: string | null = openNode(tree, tabId) ? tabId : null;
  while (cur !== null) {
    path.push(cur);
    cur = tree.nodes[cur].parent_tab_id;
  }
  return path.reverse();
}

/** 1 for a root tab, 0 when the tab is not open. */
export function depthOf(tree: TabTree, tabId: string): number {
  let depth = 0;
  let cur: string | null = openNode(tree, tabId) ? tabId : null;
  while (cur !== null) {
    depth++;
    cur = tree.nodes[cur].parent_tab_id;
  }
  return depth;
}

/** The open tab `tabId` and all its open descendants, pre-order. Iterative. */
export function subtreeIds(tree: TabTree, tabId: string): string[] {
  if (!openNode(tree, tabId)) return [];
  const out: string[] = [];
  const stack = [tabId];
  while (stack.length > 0) {
    const id = stack.pop() as string;
    out.push(id);
    const children = tree.nodes[id].child_order;
    for (let i = children.length - 1; i >= 0; i--) stack.push(children[i]);
  }
  return out;
}

/** Numbers as addresses: the open tab whose hier_number is `hier`. */
export function findByHierNumber(tree: TabTree, hier: string): string | null {
  for (const id of Object.keys(tree.nodes)) {
    if (tree.nodes[id].hier_number === hier) return id;
  }
  return null;
}

/** Where `prefix+o` goes: the last-visited child, else the first child. */
export function lastVisitedChild(tree: TabTree, tabId: string): string | null {
  const node = openNode(tree, tabId);
  if (!node) return null;
  return node.last_visited_child_id ?? node.child_order[0] ?? null;
}

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

/**
 * Open a tab as a child of `parentId`, or as a root when it is null.
 * A root gets "1", "2", …; a child of "3.2" gets "3.2.<n>" with n from that
 * parent's monotonic counter. public_number starts null: the model never
 * invents one.
 */
export function spawnChild(
  tree: TabTree,
  parentId: string | null,
  input: SpawnInput,
): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  const idProblem = tabIdProblem(input.tab_id);
  if (idProblem) return fail("invalid_tab_id", idProblem);
  if (input.mothership !== tree.mothership) {
    return fail("wrong_mothership", `tab is for ${input.mothership}, tree is ${tree.mothership}`);
  }
  if (isKnown(tree, input.tab_id)) return fail("duplicate_tab_id", `tab_id ${input.tab_id} already exists`);
  const parent = parentId === null ? undefined : openNode(tree, parentId);
  if (parentId !== null && !parent) return fail("tab_not_open", `parent ${parentId} is not open`);
  const originBad = originProblem(input.origin?.kind, input.opened_by);
  if (originBad) return fail("tab_origin_invalid", originBad);
  const side = sideForSpawn(parent, input);
  if (!kindAllowedOnSide(input.kind, side)) {
    return fail("kind_side_mismatch", `a ${side} tab cannot be of kind ${input.kind}`);
  }

  const index = nextIndex(tree, parentId);
  const hier = parent ? `${parent.hier_number}.${index}` : String(index);
  const node: TabNode = {
    tab_id: input.tab_id,
    parent_tab_id: parentId,
    side,
    ...(input.origin ? { branch_origin: input.origin } : {}),
    ...(input.opened_by ? { opened_by: input.opened_by } : {}),
    hier_number: hier,
    child_order: [],
    kind: input.kind,
    ref: input.ref,
    title: input.title ?? "",
    mothership: input.mothership,
    ...(input.pane ? { pane: input.pane } : {}),
    public_number: null,
  };
  const nodes: Record<string, TabNode> = { ...tree.nodes, [input.tab_id]: node };
  let next: TabTree;
  if (parent === undefined || parentId === null) {
    next = { ...tree, nodes, root_order: [...tree.root_order, input.tab_id], next_root_index: index + 1 };
  } else {
    nodes[parentId] = { ...parent, child_order: [...parent.child_order, input.tab_id] };
    next = { ...tree, nodes, next_child_index: { ...tree.next_child_index, [parentId]: index + 1 } };
  }
  if (input.activate ?? true) next = activate(next, input.tab_id, nodes);
  return { ok: true, tree: next, op: { type: "spawn", parent_tab_id: parentId, input, hier_number: hier } };
}

/** Part 2 §2.2: a child inherits its parent's side, except an agent-opened
 *  document and a reformat result, which are always left. A root takes the
 *  side it asks for, left by default. */
function sideForSpawn(parent: TabNode | undefined, input: SpawnInput): TabSide {
  const kind = input.origin?.kind;
  if (kind === "agent" || kind === "derivation") return "left";
  if (parent) return parent.side;
  return input.side ?? "left";
}

/** The tab holding public number `n`, open or in history, or null. */
function publicNumberHolder(tree: TabTree, n: number): string | null {
  for (const id of Object.keys(tree.nodes)) if (tree.nodes[id].public_number === n) return id;
  for (const id of Object.keys(tree.history)) if (tree.history[id].node.public_number === n) return id;
  return null;
}

/**
 * Record the number the server's allocate route returned for a tab. Refuses
 * (never throws) when another tab_id holds n, open or in history: that would
 * be reuse (R3-1). A closed tab may still receive its number, because the
 * allocation can land after the close; the number then retires with it.
 */
export function assignPublicNumber(
  tree: TabTree,
  tabId: string,
  n: number,
): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  if (!Number.isSafeInteger(n) || n < 1) return fail("public_number_invalid", `public_number must be a positive integer, got ${n}`);
  const open = openNode(tree, tabId);
  const closed = open ? undefined : closedTab(tree, tabId);
  const current = open ?? closed?.node;
  if (!current) return fail("unknown_tab", `tab ${tabId} does not exist`);
  const op: TabOp = { type: "assign_public_number", tab_id: tabId, public_number: n };
  if (current.public_number === n) return { ok: true, tree, op };
  if (current.public_number !== null) {
    return fail("already_numbered", `tab ${tabId} already has public number ${current.public_number}; numbers never change`);
  }
  const holder = publicNumberHolder(tree, n);
  if (holder !== null) return fail("public_number_taken", `public number ${n} is held by ${holder}`);
  const updated = { ...current, public_number: n };
  const next: TabTree = open
    ? { ...tree, nodes: { ...tree.nodes, [tabId]: updated } }
    : { ...tree, history: { ...tree.history, [tabId]: { ...(closed as ClosedTab), node: updated } } };
  return { ok: true, tree: next, op };
}

/**
 * Close a tab.
 *  - `prune`: the tab and its whole subtree move to history.
 *  - `lift_children`: only the tab moves to history. Its children take its
 *    place in its parent's child_order (or root_order) and keep their
 *    hier_numbers: numbers are addresses, so a lifted "3.2.1" stays "3.2.1"
 *    under "3".
 * Each history entry records `closed_at: now` and the `close_mode` the server
 * will read off the diff (see RetireMode). Nodes go to history unchanged: the
 * server, not the client, sets `pruned_at` on a pruned retirement.
 *
 * Active tab rule: if the active tab is closed (in prune mode, anywhere in the
 * subtree), focus moves to the closed tab's parent; for a root, to the root
 * just before it, else the root now in its place (the next root, or in lift
 * mode its first lifted child), else null. Otherwise focus does not move.
 *
 * `closeId` names this close for undo. The default is unique per tab and
 * timestamp; pass one if the same tab can close twice at the same `now`.
 */
export function closeTab(
  tree: TabTree,
  tabId: string,
  mode: CloseMode,
  now: string,
  closeId = `${tabId}@${now}`,
  seenTabIds?: readonly string[],
): TabTreeResult<{ tree: TabTree; undo: UndoToken; op: TabOp }> {
  const x = openNode(tree, tabId);
  if (!x) return fail("tab_not_open", `tab ${tabId} is not open`);
  const parentId = x.parent_tab_id;
  const siblings = siblingsOf(tree, parentId);
  const index = siblings.indexOf(tabId);
  const seen = seenTabIds === undefined ? null : new Set(seenTabIds);
  const removed = mode === "prune" ? subtreeIds(tree, tabId).filter((id) => seen === null || seen.has(id)) : [tabId];
  const removedSet = new Set(removed);
  const lifted = mode === "prune"
    ? subtreeIds(tree, tabId).filter((id) => !removedSet.has(id) && removedSet.has(tree.nodes[id].parent_tab_id ?? ""))
    : x.child_order;
  const newSiblings = [...siblings.slice(0, index), ...lifted, ...siblings.slice(index + 1)];

  const nodes: Record<string, TabNode> = {};
  for (const id of Object.keys(tree.nodes)) if (!removedSet.has(id)) nodes[id] = tree.nodes[id];
  for (const c of lifted) nodes[c] = { ...nodes[c], parent_tab_id: parentId };
  let parentRememberedIt = false;
  if (parentId !== null) {
    const parent = nodes[parentId];
    parentRememberedIt = parent.last_visited_child_id === tabId;
    const updated = parentRememberedIt ? withoutLastVisited(parent) : parent;
    nodes[parentId] = { ...updated, child_order: newSiblings };
  }
  const history: Record<string, ClosedTab> = { ...tree.history };
  const headMode: RetireMode = x.child_order.length === 0 ? "close" : mode === "prune" ? "prune" : "lift_children";
  for (const id of removed) {
    let node: TabNode = { ...tree.nodes[id], pruned_at: now };
    if (mode === "prune" && lifted.length > 0) {
      node = { ...node, child_order: node.child_order.filter((c) => removedSet.has(c)) };
      if (node.last_visited_child_id && !removedSet.has(node.last_visited_child_id)) node = withoutLastVisited(node);
    }
    history[id] = { node, close_id: closeId, closed_at: now, close_mode: id === tabId ? headMode : "prune" };
  }

  let active = tree.active_tab_id;
  if (active !== null && removedSet.has(active)) {
    if (parentId !== null) active = parentId;
    else if (index > 0) active = newSiblings[index - 1];
    else active = newSiblings[index] ?? null;
  }

  const next: TabTree = {
    ...tree,
    nodes,
    root_order: parentId === null ? newSiblings : tree.root_order,
    history,
    active_tab_id: active,
    active_right: tree.active_right !== null && removedSet.has(tree.active_right) ? (active !== null && nodes[active]?.side === "right" ? active : null) : tree.active_right,
    active_left: tree.active_left !== null && removedSet.has(tree.active_left) ? (active !== null && nodes[active]?.side === "left" ? active : null) : tree.active_left,
  };
  const token: UndoToken = {
    close_id: closeId,
    mode,
    tab_id: tabId,
    parent_tab_id: parentId,
    index,
    prev_sibling_id: index > 0 ? siblings[index - 1] : null,
    next_sibling_id: index + 1 < siblings.length ? siblings[index + 1] : null,
    prev_active_tab_id: tree.active_tab_id,
    prev_active_right: tree.active_right,
    prev_active_left: tree.active_left,
    parent_remembered_it: parentRememberedIt,
  };
  return { ok: true, tree: next, undo: token, op: { type: "close", close_id: closeId, tab_id: tabId, mode, now, seen_tab_ids: seenTabIds ?? removed } };
}

/** The nearest open tab at or above `id`, walking closed tabs' recorded
 *  parents. null means "root". Iterative. */
function nearestOpenAncestor(tree: TabTree, id: string | null): string | null {
  let cur = id;
  const seen = new Set<string>();
  while (cur !== null) {
    if (openNode(tree, cur)) return cur;
    const closed = closedTab(tree, cur);
    if (!closed || seen.has(cur)) return null;
    seen.add(cur);
    cur = closed.node.parent_tab_id;
  }
  return null;
}

/**
 * Put one close back. Straight after the close this restores the tree
 * exactly (deep-equal, version included) with the same numbers on the same
 * tab_ids (I6). After other operations it still restores the closed tabs with
 * their numbers:
 *  - The tab goes back under its recorded parent, next to its recorded
 *    neighbours. If that parent has closed since, it goes under the nearest
 *    open ancestor (appended), as a lifted child would.
 *  - Undoing a lift takes back those original children that are still open,
 *    wherever they are now.
 *  - Focus returns to the tab that was active at close time if the undo
 *    reopened it; otherwise focus does not move.
 * Refuses a token whose close is not the one that put the tab in history
 * (already undone, or superseded by a later close).
 */
export function undo(tree: TabTree, token: UndoToken, restoreRetired = false): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  const entry = closedTab(tree, token.tab_id);
  if (!entry || entry.close_id !== token.close_id) {
    return fail("not_closed_by_token", `tab ${token.tab_id} is not closed by ${token.close_id}`);
  }
  // The tabs this close moved to history, by walking the closed records.
  const restore: string[] = [];
  const stack = [token.tab_id];
  while (stack.length > 0) {
    const id = stack.pop() as string;
    const rec = closedTab(tree, id);
    if (!rec || rec.close_id !== token.close_id) continue;
    restore.push(id);
    if (token.mode === "prune") for (const c of rec.node.child_order) stack.push(c);
  }
  const restoreSet = new Set(restore);

  const nodes: Record<string, TabNode> = { ...tree.nodes };
  let rootOrder: string[] = [...tree.root_order];
  const history: Record<string, ClosedTab> = {};
  for (const id of Object.keys(tree.history)) if (!restoreSet.has(id)) history[id] = tree.history[id];
  for (const id of restore) {
    nodes[id] = restoreRetired ? tree.history[id].node
      : tree.restoring?.[id] ? { ...tree.history[id].node, pruned_at: tree.restoring[id].pruned_at }
        : withoutPrunedAt(tree.history[id].node);
  }

  const detach = (childId: string, fromParent: string | null) => {
    if (fromParent === null) {
      rootOrder = rootOrder.filter((id) => id !== childId);
      return;
    }
    const p = nodes[fromParent];
    const base = p.last_visited_child_id === childId ? withoutLastVisited(p) : p;
    nodes[fromParent] = { ...base, child_order: base.child_order.filter((id) => id !== childId) };
  };

  const x = nodes[token.tab_id];
  if (token.mode === "lift_children") {
    // Take back the original children that are still open.
    const back = x.child_order.filter((c) => Object.hasOwn(tree.nodes, c));
    for (const c of back) {
      detach(c, nodes[c].parent_tab_id);
      nodes[c] = { ...nodes[c], parent_tab_id: token.tab_id };
    }
    let restored: TabNode = { ...x, child_order: back };
    if (restored.last_visited_child_id !== undefined && !back.includes(restored.last_visited_child_id)) {
      restored = withoutLastVisited(restored);
    }
    nodes[token.tab_id] = restored;
  }

  // Re-attach the tab under its recorded parent, or the nearest open ancestor.
  const target = nearestOpenAncestor(tree, token.parent_tab_id);
  const exact = target === token.parent_tab_id;
  const list = target === null ? rootOrder : [...nodes[target].child_order];
  let at: number;
  if (!exact) at = list.length;
  else if (token.prev_sibling_id !== null && list.includes(token.prev_sibling_id)) at = list.indexOf(token.prev_sibling_id) + 1;
  else if (token.next_sibling_id !== null && list.includes(token.next_sibling_id)) at = list.indexOf(token.next_sibling_id);
  else at = Math.min(token.index, list.length);
  const inserted = [...list.slice(0, at), token.tab_id, ...list.slice(at)];
  nodes[token.tab_id] = { ...nodes[token.tab_id], parent_tab_id: target };
  if (target === null) rootOrder = inserted;
  else {
    const p = nodes[target];
    const remember = exact && token.parent_remembered_it && p.last_visited_child_id === undefined;
    nodes[target] = { ...p, child_order: inserted, ...(remember ? { last_visited_child_id: token.tab_id } : {}) };
  }

  const active =
    token.prev_active_tab_id !== null && restoreSet.has(token.prev_active_tab_id) ? token.prev_active_tab_id : tree.active_tab_id;
  const prevRight = token.prev_active_right ?? null;
  const activeRight = prevRight !== null && restoreSet.has(prevRight) ? prevRight : tree.active_right;
  const next: TabTree = { ...tree, nodes, root_order: rootOrder, history, active_tab_id: active, active_right: activeRight,
    active_left: token.prev_active_left && restoreSet.has(token.prev_active_left) ? token.prev_active_left : tree.active_left };
  if (restoreRetired) {
    const restoring = { ...tree.restoring };
    for (const id of restore) restoring[id] = tree.history[id].node;
    next.restoring = restoring;
  }
  return { ok: true, tree: next, op: { type: "undo", token, ...(restoreRetired ? { restore_retired: true } : {}) } };
}

/**
 * The most recently closed tab that heads its close: the tab a close was
 * called on (a pruned subtree's other tabs share its close and its time, and
 * come back with it). Ties on time go to the later entry. null = nothing
 * retired.
 */
export function lastRetired(tree: TabTree): string | null {
  let best: { id: string; at: string } | null = null;
  for (const id of Object.keys(tree.history)) {
    const entry = tree.history[id];
    const parent = entry.node.parent_tab_id;
    const parentEntry = parent !== null ? closedTab(tree, parent) : undefined;
    // A tab pruned WITH its parent comes back with the parent.
    if (parentEntry && parentEntry.close_id === entry.close_id) continue;
    const at = entry.closed_at;
    if (best === null || at >= best.at) best = { id, at };
  }
  return best?.id ?? null;
}

/**
 * Bring a retired tab back after its undo window (contract §2.2: restore
 * from `retired`). It is the long-lived half of undo and needs no token:
 *  - the tab returns with the tabs its own close retired with it (a pruned
 *    subtree), each with its own tab_id and numbers (R3-1: not reuse);
 *  - a child that was lifted out, closed separately or reopened since stays
 *    where it is: each restored tab keeps only restored children;
 *  - it goes back under its recorded parent, or the nearest open ancestor,
 *    or the roots, appended (its old neighbours may be long gone);
 *  - it becomes the active tab: reopening is a request to see it.
 * `closeId`, when given, must be the close that retired it (a rebase replay).
 */
export function restoreClosed(
  tree: TabTree,
  tabId: string,
  closeId?: string,
): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  const entry = closedTab(tree, tabId);
  if (!entry || (closeId !== undefined && entry.close_id !== closeId)) {
    return fail("not_closed_by_token", `tab ${tabId} is not retired${closeId ? ` by ${closeId}` : ""}`);
  }
  const restore: string[] = [];
  const stack = [tabId];
  while (stack.length > 0) {
    const id = stack.pop() as string;
    const rec = closedTab(tree, id);
    if (!rec || rec.close_id !== entry.close_id || restore.includes(id)) continue;
    restore.push(id);
    for (const c of rec.node.child_order) stack.push(c);
  }
  const restoreSet = new Set(restore);
  const nodes: Record<string, TabNode> = { ...tree.nodes };
  const history: Record<string, ClosedTab> = {};
  for (const id of Object.keys(tree.history)) if (!restoreSet.has(id)) history[id] = tree.history[id];
  for (const id of restore) {
    let node: TabNode = tree.history[id].node;
    const kept = node.child_order.filter((c) => restoreSet.has(c));
    node = { ...node, child_order: kept };
    if (node.last_visited_child_id !== undefined && !kept.includes(node.last_visited_child_id)) {
      node = withoutLastVisited(node);
    }
    nodes[id] = node;
  }
  const target = nearestOpenAncestor(tree, entry.node.parent_tab_id);
  nodes[tabId] = { ...nodes[tabId], parent_tab_id: target };
  let rootOrder = tree.root_order;
  if (target === null) rootOrder = [...tree.root_order, tabId];
  else nodes[target] = { ...nodes[target], child_order: [...nodes[target].child_order, tabId] };
  const restoring = { ...tree.restoring };
  for (const id of restore) restoring[id] = tree.history[id].node;
  const next = activate({ ...tree, nodes, root_order: rootOrder, history, restoring }, tabId);
  return { ok: true, tree: next, op: { type: "restore", tab_id: tabId, close_id: entry.close_id } };
}

/** Focus a tab (or nothing), remembering the path to it: every ancestor's
 *  last_visited_child_id points down toward it. */
export function setActive(tree: TabTree, tabId: string | null): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  if (tabId !== null && !openNode(tree, tabId)) return fail("tab_not_open", `tab ${tabId} is not open`);
  return { ok: true, tree: activate(tree, tabId), op: { type: "set_active", tab_id: tabId } };
}

/** `prefix+o`: focus the last-visited child of `tabId`, else its first child. */
export function visitChild(tree: TabTree, tabId: string): TabTreeResult<{ tree: TabTree; op: TabOp }> {
  if (!openNode(tree, tabId)) return fail("tab_not_open", `tab ${tabId} is not open`);
  const child = lastVisitedChild(tree, tabId);
  if (child === null) return fail("no_children", `tab ${tabId} has no children`);
  return setActive(tree, child);
}

// ---------------------------------------------------------------------------
// Rebase after a 409 (contract Part 2 §2.2 "rebasing")
// ---------------------------------------------------------------------------

export interface DroppedOp {
  op: TabOp;
  /** The error code that made the op inapplicable on the remote tree,
   *  usually "tab_not_open": another device closed its tab. */
  reason: TabTreeErrorCode;
}

export interface RebaseResult {
  tree: TabTree;
  /** Ops that no longer apply; the UI reports their reasons without a modal. */
  dropped: DroppedOp[];
  /** Tabs reattached because their parent closed; the UI names the destination. */
  reparented: { tab_id: string; parent_tab_id: string | null; reason: "closed_parent" | "unseen_child" }[];
  /** Pending spawns whose hier_number changed under the remote counters. */
  renumbered: { tab_id: string; from: string; to: string }[];
}

/**
 * Replay pending local ops onto the tree a 409 returned.
 *  - A spawn is never lost. If its parent closed remotely, it goes under the
 *    nearest surviving ancestor (or becomes a root). Its hier_number is
 *    recomputed under the remote counters, because another device may have
 *    spawned under the same parent; it was never final (R3-5).
 *  - An op on a tab the remote closed is dropped and reported.
 *  - A replayed prune closes only the recorded visible subtree. Unseen
 *    remote children lift to its parent and retain their own descendants.
 * The result keeps the remote's version, ready for the next PUT.
 */
export function rebase(remote: TabTree, pending: readonly TabOp[]): RebaseResult {
  let tree = remote;
  const dropped: DroppedOp[] = [];
  const renumbered: RebaseResult["renumbered"] = [];
  const reparented: RebaseResult["reparented"] = [];
  const replayedCloses = new Map<string, UndoToken>();
  for (const op of pending) {
    switch (op.type) {
      case "spawn": {
        const parent = nearestOpenAncestor(tree, op.parent_tab_id);
        const r = spawnChild(tree, parent, op.input);
        if (!r.ok) {
          dropped.push({ op, reason: r.error.code });
          break;
        }
        tree = r.tree;
        if (parent !== op.parent_tab_id) reparented.push({ tab_id: op.input.tab_id, parent_tab_id: parent, reason: "closed_parent" });
        const now = tree.nodes[op.input.tab_id].hier_number;
        if (now !== op.hier_number) renumbered.push({ tab_id: op.input.tab_id, from: op.hier_number, to: now });
        break;
      }
      case "close": {
        const r = closeTab(tree, op.tab_id, op.mode, op.now, op.close_id, op.seen_tab_ids);
        if (!r.ok) {
          dropped.push({ op, reason: r.error.code });
          break;
        }
        for (const id of Object.keys(r.tree.nodes)) {
          if (op.mode === "prune" && tree.nodes[id]?.parent_tab_id !== r.tree.nodes[id].parent_tab_id) {
            reparented.push({ tab_id: id, parent_tab_id: r.tree.nodes[id].parent_tab_id, reason: "unseen_child" });
          }
        }
        tree = r.tree;
        replayedCloses.set(op.close_id, r.undo);
        break;
      }
      case "undo": {
        const token = replayedCloses.get(op.token.close_id) ?? op.token;
        const r = undo(tree, token, op.restore_retired);
        if (!r.ok) {
          dropped.push({ op, reason: r.error.code });
          break;
        }
        tree = r.tree;
        break;
      }
      case "restore": {
        const r = restoreClosed(tree, op.tab_id, op.close_id);
        if (!r.ok) dropped.push({ op, reason: r.error.code });
        else tree = r.tree;
        break;
      }
      case "assign_public_number": {
        const r = assignPublicNumber(tree, op.tab_id, op.public_number);
        if (!r.ok) dropped.push({ op, reason: r.error.code });
        else tree = r.tree;
        break;
      }
      case "set_active": {
        const r = setActive(tree, op.tab_id);
        if (!r.ok) dropped.push({ op, reason: r.error.code });
        else tree = r.tree;
        break;
      }
    }
  }
  return { tree, dropped, renumbered, reparented };
}

// ---------------------------------------------------------------------------
// Snapshot (contract §1.6)
// ---------------------------------------------------------------------------

/** A retired number, kept with the tab_id that holds it: R3-1 defines reuse
 *  per tab_id, so a bare list of numbers could not tell undo from reuse. */
export interface RetiredNumber {
  tab_id: string;
  hier_number: string;
  public_number: number | null;
}

/** The model's own JSON snapshot: the currency every TabTreeAdapter speaks
 *  (the in-memory stand-in stores it; the HTTP adapter maps it to and from
 *  the server's §1.6 wire in tabTreeWire.ts). Branch kinds use wire names
 *  ("selection"). It is NOT the server's shape: that one has no history. */
export type WireTabNode = Omit<TabNode<WireBranchKind>, "side"> & { side?: TabSide };

export interface WireTabTree {
  mothership: Mothership;
  nodes: Record<string, WireTabNode>;
  root_order: string[];
  history: Record<string, Omit<ClosedTab<WireBranchKind>, "node"> & { node: WireTabNode }>;
  next_root_index: number;
  next_child_index: Record<string, number>;
}

export interface TabTreeSnapshot {
  tree: WireTabTree;
  active_tab_id: string | null;
  /** The server's active.right (absent = null). */
  active_right?: string | null;
  active_left?: string | null;
  restoring?: Readonly<Record<string, TabNode>>;
  retired_numbers: RetiredNumber[];
  version: number;
}

function mapOrigin<A extends string, B extends string>(node: TabNode<A>, f: (k: A) => B): TabNode<B> {
  const { branch_origin, ...rest } = node;
  if (!branch_origin) return rest as TabNode<B>;
  return { ...rest, branch_origin: { ...branch_origin, kind: f(branch_origin.kind) } };
}

/** A wire node as a model node: a legacy row without `side` reads as left. */
function withoutPrunedAt(node: TabNode): TabNode {
  const { pruned_at: _timestamp, ...rest } = node;
  return rest;
}

function fromWireNode(node: WireTabNode): TabNode {
  return mapOrigin({ ...node, side: node.side === "right" ? "right" : "left" }, fromWireKind);
}

export function retiredNumbers(tree: TabTree): RetiredNumber[] {
  return Object.keys(tree.history).map((id) => {
    const n = tree.history[id].node;
    return { tab_id: id, hier_number: n.hier_number, public_number: n.public_number };
  });
}

export function toSnapshot(tree: TabTree): TabTreeSnapshot {
  const nodes: Record<string, TabNode<WireBranchKind>> = {};
  for (const id of Object.keys(tree.nodes)) nodes[id] = mapOrigin(tree.nodes[id], toWireKind);
  const history: Record<string, ClosedTab<WireBranchKind>> = {};
  for (const id of Object.keys(tree.history)) {
    history[id] = { ...tree.history[id], node: mapOrigin(tree.history[id].node, toWireKind) };
  }
  return {
    tree: {
      mothership: tree.mothership,
      nodes,
      root_order: [...tree.root_order],
      history,
      next_root_index: tree.next_root_index,
      next_child_index: { ...tree.next_child_index },
    },
    active_tab_id: tree.active_tab_id,
    active_right: tree.active_right,
    active_left: tree.active_left,
    ...(tree.restoring ? { restoring: tree.restoring } : {}),
    retired_numbers: retiredNumbers(tree),
    version: tree.version,
  };
}

/** A node from a snapshot, with the rev-7 fields a hand-built or older
 *  snapshot may lack filled in (left side, empty title). */
function normalizeNode(n: TabNode): TabNode {
  if (n.side !== undefined && n.title !== undefined) return n;
  return { ...n, side: n.side ?? "left", title: n.title ?? "" };
}

/** Parse a snapshot from the server. Refuses one holding a tab_id outside
 *  §1.6's alphabet (`invalid_tab_id`), and one that breaks an invariant,
 *  names an unknown branch kind, or whose retired_numbers disagree with its
 *  history (`invalid_snapshot`). Every tree the store holds comes through
 *  here, the HTTP adapter's `fromWire` output included. */
export function fromSnapshot(snapshot: TabTreeSnapshot): TabTreeResult<{ tree: TabTree }> {
  const w = snapshot?.tree;
  if (!w || typeof w !== "object" || typeof w.nodes !== "object" || typeof w.history !== "object" || !Array.isArray(w.root_order)) {
    return fail("invalid_snapshot", "snapshot.tree is malformed");
  }
  // Every tab_id, open or retired, keys and nodes alike, is one the server
  // accepts (§1.6): a structural id is refused here, before it reaches a tree.
  const ids = new Set<string>([...Object.keys(w.nodes), ...Object.keys(w.history)]);
  for (const n of [...Object.values(w.nodes), ...Object.values(w.history).map((e) => e?.node)]) {
    if (n && typeof n.tab_id === "string") ids.add(n.tab_id);
  }
  const badIds = [...ids].map(tabIdProblem).filter((p): p is string => p !== null);
  if (badIds.length > 0) return fail("invalid_tab_id", badIds.join("; "));
  const problems: string[] = [];
  const all = [
    ...Object.keys(w.nodes).map((id) => w.nodes[id]),
    ...Object.keys(w.history).map((id) => w.history[id]?.node),
  ];
  for (const n of all) {
    if (!n || typeof n.tab_id !== "string" || typeof n.hier_number !== "string" || !Array.isArray(n.child_order)) {
      problems.push("a node is malformed");
      continue;
    }
    if (n.branch_origin && !WIRE_KINDS.has(n.branch_origin.kind)) {
      problems.push(`${n.tab_id}: unknown branch kind ${JSON.stringify(n.branch_origin.kind)}`);
    }
    if (n.side !== undefined && n.side !== "left" && n.side !== "right") {
      problems.push(`${n.tab_id}: unknown side ${JSON.stringify(n.side)}`);
    }
    const originBad = originProblem(n.branch_origin?.kind, n.opened_by);
    if (originBad) problems.push(`${n.tab_id}: ${originBad}`);
  }
  if (problems.length > 0) return fail("invalid_snapshot", problems.join("; "));

  const nodes: Record<string, TabNode> = {};
  for (const id of Object.keys(w.nodes)) nodes[id] = normalizeNode(fromWireNode(w.nodes[id]));
  const history: Record<string, ClosedTab> = {};
  for (const id of Object.keys(w.history)) {
    history[id] = { ...w.history[id], node: normalizeNode(fromWireNode(w.history[id].node)) };
  }
  const tree: TabTree = {
    mothership: w.mothership,
    nodes,
    root_order: [...w.root_order],
    active_tab_id: snapshot.active_tab_id,
    active_right: snapshot.active_right ?? null,
    active_left: snapshot.active_left === undefined ? (snapshot.active_tab_id && nodes[snapshot.active_tab_id]?.side === "left" ? snapshot.active_tab_id : null) : snapshot.active_left,
    ...(snapshot.restoring ? { restoring: snapshot.restoring } : {}),
    history,
    next_root_index: w.next_root_index,
    next_child_index: { ...w.next_child_index },
    version: snapshot.version,
  };
  const violations = checkInvariants(tree);
  if (!Number.isSafeInteger(tree.version) || tree.version < 0) violations.push("invalid version");
  if (!Number.isSafeInteger(tree.next_root_index) || tree.next_root_index < 1) violations.push("invalid root counter");
  if (Object.entries(tree.next_child_index).some(([id, count]) => !isLegalTabId(id) || !Number.isSafeInteger(count) || count < 1)) violations.push("invalid child counter");
  const key = (r: RetiredNumber) => `${r.tab_id}\u0000${r.hier_number}\u0000${r.public_number}`;
  const claimed = (snapshot.retired_numbers ?? []).map(key).sort();
  const derived = retiredNumbers(tree).map(key).sort();
  if (JSON.stringify(claimed) !== JSON.stringify(derived)) violations.push("retired_numbers disagree with history");
  if (violations.length > 0) return fail("invalid_snapshot", violations.join("; "));
  return { ok: true, tree };
}

// ---------------------------------------------------------------------------
// Invariants (enumerated in tabTree.property.test.ts)
// ---------------------------------------------------------------------------

const HIER_RE = /^[1-9][0-9]*(\.[1-9][0-9]*)*$/;

function isProperPrefix(ancestor: string, hier: string): boolean {
  return hier.length > ancestor.length && hier.startsWith(ancestor) && hier.charCodeAt(ancestor.length) === 46; // "."
}

/** Single-state invariants I1, I2, I4, I5, I8, I9. Empty list = OK. Iterative. */
export function checkInvariants(tree: TabTree): string[] {
  const v: string[] = [];
  const openIds = Object.keys(tree.nodes);
  const closedIds = Object.keys(tree.history);

  // I5: keys, disjointness, mothership, side, retirement record. pruned_at
  // is the server's (rev 8.8): an open tab carries it only while a restore
  // is on its way to the server, so it is not an I5 fault either way.
  for (const id of openIds) {
    const n = tree.nodes[id];
    if (n.tab_id !== id) v.push(`I5: open key ${id} holds tab ${n.tab_id}`);
    if (Object.hasOwn(tree.history, id)) v.push(`I5: ${id} is both open and closed`);
    if (n.mothership !== tree.mothership) v.push(`I5: ${id} belongs to ${n.mothership}`);
    if (n.pruned_at !== undefined && n.pruned_at !== tree.restoring?.[id]?.pruned_at) v.push(`I5: open tab ${id} has pruned_at without a pending restore`);
    if (n.side !== "left" && n.side !== "right") v.push(`I5: ${id} has no side`);
    else if (!kindAllowedOnSide(n.kind, n.side)) v.push(`I5: ${id} has invalid kind for its side`);
  }
  for (const id of closedIds) {
    const entry = tree.history[id];
    const n = entry.node;
    if (n.tab_id !== id) v.push(`I5: history key ${id} holds tab ${n.tab_id}`);
    if (n.mothership !== tree.mothership) v.push(`I5: closed ${id} belongs to ${n.mothership}`);
    if (!kindAllowedOnSide(n.kind, n.side)) v.push(`I5: closed ${id} has invalid kind for its side`);
    if (typeof entry.closed_at !== "string") v.push(`I5: closed tab ${id} has no closed_at`);
    if (entry.close_mode !== "close" && entry.close_mode !== "prune" && entry.close_mode !== "lift_children") {
      v.push(`I5: closed tab ${id} has close_mode ${String(entry.close_mode)}`);
    }
  }

  // I5: root_order <=> roots; child_order <=> parent_tab_id.
  const seenRoot = new Set<string>();
  for (const id of tree.root_order) {
    const n = openNode(tree, id);
    if (!n) v.push(`I5: root_order names ${id}, which is not open`);
    else if (n.parent_tab_id !== null) v.push(`I5: root_order names ${id}, whose parent is ${n.parent_tab_id}`);
    if (seenRoot.has(id)) v.push(`I5: ${id} twice in root_order`);
    seenRoot.add(id);
  }
  for (const id of openIds) {
    const n = tree.nodes[id];
    if (n.parent_tab_id === null) {
      if (!seenRoot.has(id)) v.push(`I5: root ${id} missing from root_order`);
    } else {
      const p = openNode(tree, n.parent_tab_id);
      if (!p) v.push(`I5: ${id} has parent ${n.parent_tab_id}, which is not open`);
      else {
        if (!p.child_order.includes(id)) v.push(`I5: ${id} missing from ${n.parent_tab_id}.child_order`);
        // I9: the parent is a spawn-ancestor.
        if (!isProperPrefix(p.hier_number, n.hier_number)) v.push(`I9: parent ${p.hier_number} is not a prefix of ${n.hier_number}`);
      }
    }
    const seenChild = new Set<string>();
    for (const c of n.child_order) {
      const child = openNode(tree, c);
      if (!child) v.push(`I5: ${id}.child_order names ${c}, which is not open`);
      else if (child.parent_tab_id !== id) v.push(`I5: ${id}.child_order names ${c}, whose parent is ${child.parent_tab_id}`);
      if (seenChild.has(c)) v.push(`I5: ${c} twice in ${id}.child_order`);
      seenChild.add(c);
    }
    if (n.last_visited_child_id !== undefined && !seenChild.has(n.last_visited_child_id)) {
      v.push(`I5: ${id}.last_visited_child_id ${n.last_visited_child_id} is not its child`);
    }
  }
  // I5: no cycles: every open tab is reached exactly once from the roots.
  const reached = new Set<string>();
  const stack = [...tree.root_order].filter((id) => openNode(tree, id));
  while (stack.length > 0) {
    const id = stack.pop() as string;
    if (reached.has(id)) {
      v.push(`I5: ${id} reached twice`);
      continue;
    }
    reached.add(id);
    for (const c of tree.nodes[id].child_order) if (openNode(tree, c)) stack.push(c);
  }
  if (reached.size !== openIds.length) v.push(`I5: ${openIds.length - reached.size} open tab(s) unreachable from the roots (cycle or orphan)`);

  // I1, I2: numbers unique across open + history.
  const byHier = new Map<string, string>();
  const byPublic = new Map<number, string>();
  const everyNode: TabNode[] = [...openIds.map((id) => tree.nodes[id]), ...closedIds.map((id) => tree.history[id].node)];
  for (const n of everyNode) {
    if (!HIER_RE.test(n.hier_number)) v.push(`I1: ${n.tab_id} has malformed hier_number ${n.hier_number}`);
    const h = byHier.get(n.hier_number);
    if (h !== undefined) v.push(`I1: hier_number ${n.hier_number} held by ${h} and ${n.tab_id}`);
    else byHier.set(n.hier_number, n.tab_id);
    if (n.public_number !== null) {
      if (!Number.isSafeInteger(n.public_number) || n.public_number < 1) v.push(`I2: ${n.tab_id} has invalid public_number ${n.public_number}`);
      const p = byPublic.get(n.public_number);
      if (p !== undefined) v.push(`I2: public_number ${n.public_number} held by ${p} and ${n.tab_id}`);
      else byPublic.set(n.public_number, n.tab_id);
    }
  }

  // I4: each counter is above every index issued under its parent.
  for (const n of everyNode) {
    const dot = n.hier_number.lastIndexOf(".");
    const last = Number(n.hier_number.slice(dot + 1));
    if (dot < 0) {
      if (!(tree.next_root_index > last)) v.push(`I4: root counter ${tree.next_root_index} not above ${n.hier_number}`);
      continue;
    }
    const spawnParent = byHier.get(n.hier_number.slice(0, dot));
    // The spawn parent can be unknown: the server's retired[] is a window of
    // the 200 most recent retirements (§1.6), so an old parent may be off it.
    // Its counter then lives only on the server, which checks it.
    if (spawnParent === undefined) continue;
    const counter = Object.hasOwn(tree.next_child_index, spawnParent) ? tree.next_child_index[spawnParent] : 1;
    if (!(counter > last)) v.push(`I4: counter of ${spawnParent} is ${counter}, not above ${n.hier_number}`);
  }
  // I9 for closed tabs: the recorded parent was a spawn-ancestor too.
  for (const id of closedIds) {
    const n = tree.history[id].node;
    if (n.parent_tab_id === null) continue;
    const p = openNode(tree, n.parent_tab_id) ?? closedTab(tree, n.parent_tab_id)?.node;
    if (p && !isProperPrefix(p.hier_number, n.hier_number)) v.push(`I9: closed ${id}'s parent ${p.hier_number} is not a prefix of ${n.hier_number}`);
  }

  // I8: active is null or open; the right pane's active is null or an open
  // right tab (§1.6: "active.right is null or an open tab on that side").
  if (tree.active_tab_id !== null && !openNode(tree, tree.active_tab_id)) v.push(`I8: active ${tree.active_tab_id} is not open`);
  if (tree.active_left !== null && openNode(tree, tree.active_left)?.side !== "left") v.push("I8: active_left is not an open left tab");
  if (tree.active_right !== null && openNode(tree, tree.active_right)?.side !== "right") {
    v.push(`I8: active_right ${tree.active_right} is not an open right tab`);
  }
  return v;
}

/**
 * Reuse as contract R3-1 defines it: a number `before` held (open or retired)
 * that `after` gives to a DIFFERENT tab_id. The same tab_id getting its own
 * number back (undo) is not reuse.
 */
export function numberReuse(before: TabTree, after: TabTree): string[] {
  const hierHolder = new Map<string, string>();
  const publicHolder = new Map<number, string>();
  const scan = (n: TabNode) => {
    hierHolder.set(n.hier_number, n.tab_id);
    if (n.public_number !== null) publicHolder.set(n.public_number, n.tab_id);
  };
  for (const id of Object.keys(after.nodes)) scan(after.nodes[id]);
  for (const id of Object.keys(after.history)) scan(after.history[id].node);
  const out: string[] = [];
  const check = (n: TabNode) => {
    const h = hierHolder.get(n.hier_number);
    if (h !== undefined && h !== n.tab_id) out.push(`hier_number ${n.hier_number} moved from ${n.tab_id} to ${h}`);
    if (n.public_number !== null) {
      const p = publicHolder.get(n.public_number);
      if (p !== undefined && p !== n.tab_id) out.push(`public_number ${n.public_number} moved from ${n.tab_id} to ${p}`);
    }
  };
  for (const id of Object.keys(before.nodes)) check(before.nodes[id]);
  for (const id of Object.keys(before.history)) check(before.history[id].node);
  return out;
}

// ---------------------------------------------------------------------------
// Persistence adapter (contract §1.6)
// ---------------------------------------------------------------------------

/** The PUT's outcomes, in the model's terms (the server's §1.6 answers):
 *  - `saved`: the server's snapshot, so its version, numbers and retired
 *    entries replace the local ones;
 *  - `conflict`: 409 `version_stale` (another device wrote first) or
 *    `number_conflict` (a pending number the register gives another tab).
 *    Both rebase the same way onto `current`;
 *  - `invalid`: 422 `tab_origin_invalid` | `tab_tree_invalid`. Part 2 §2.2:
 *    a lane-A bug. Log the detail, refetch and rebase; never tell the
 *    operator it is their error. */
export type SaveResult =
  | { status: "saved"; snapshot: TabTreeSnapshot }
  | {
      status: "conflict";
      reason: "version_stale" | "number_conflict";
      current: TabTreeSnapshot;
      tab_id?: string;
      detail?: string;
    }
  | { status: "invalid"; reason: "tab_origin_invalid" | "tab_tree_invalid"; tab_id: string | null; detail: string };

/** One page of older retirements, newest first. `next_before` is null on
 *  the last page (§1.6 rev 8.8), including an exactly full one. */
export interface RetiredPage {
  entries: ClosedTab[];
  next_before: string | null;
}

/**
 * GET /projects/{id}/tabs/{mothership}, PUT with expected_version,
 * POST …/allocate {tab_id} and GET …/retired. `createHttpTabTreeAdapter`
 * (tabTreeHttpAdapter.ts) drives lane B's routes; `createInMemoryTabTreeAdapter`
 * stands in where they are not deployed. No implementation may use
 * localStorage or sessionStorage (§1.6).
 */
export interface TabTreeAdapter {
  load(projectId: string, mothership: Mothership, signal?: AbortSignal): Promise<TabTreeSnapshot>;
  /** `snapshot.version` is the expected_version. */
  save(projectId: string, mothership: Mothership, snapshot: TabTreeSnapshot, signal?: AbortSignal): Promise<SaveResult>;
  /** Workstation-wide (per project, across motherships), monotonic, never
   *  reused, and idempotent per tab_id: a retry after a lost response
   *  returns the same number. */
  allocate(projectId: string, mothership: Mothership, tabId: string, signal?: AbortSignal): Promise<{ public_number: number }>;
  /** Older retirements than `load` carries, before `before` (null = the
   *  newest page). Absent on an adapter whose load holds all of history. */
  retired?(projectId: string, mothership: Mothership, before: string | null, signal?: AbortSignal): Promise<RetiredPage>;
}

/**
 * The in-memory stand-in for lane B's routes. It enforces what the contract
 * says the server enforces, with the server's answer shapes: optimistic
 * concurrency (409 `version_stale` with the current snapshot), a number the
 * register gives another tab (409 `number_conflict`), a public number it
 * never allocated and `pruned_at` on a tab that is not being restored (422
 * `tab_tree_invalid`, rev 8.8). On accept it does what the server does to the
 * retirement rows: a restored tab's `pruned_at` is cleared, and a new pruned
 * retirement's node gets `pruned_at` = its `closed_at`. Rows are stored as
 * JSON so no caller can alias server state.
 */
export function createInMemoryTabTreeAdapter(): TabTreeAdapter {
  const rows = new Map<string, string>();
  /** Every number ever accepted, with its tab_id: hier per row, public per project. */
  const hierHolders = new Map<string, Map<string, string>>();
  const publicHolders = new Map<string, Map<number, string>>();
  const nextPublic = new Map<string, number>();
  /** allocate is idempotent per tab_id: project → tab_id → number. */
  const allocated = new Map<string, Map<string, number>>();
  const rowKey = (projectId: string, mothership: Mothership) => `${projectId}\u0000${mothership}`;
  const mapFor = <K, V = string>(store: Map<string, Map<K, V>>, key: string): Map<K, V> => {
    let m = store.get(key);
    if (!m) {
      m = new Map();
      store.set(key, m);
    }
    return m;
  };
  const current = (projectId: string, mothership: Mothership): TabTreeSnapshot => {
    const row = rows.get(rowKey(projectId, mothership));
    return row ? (JSON.parse(row) as TabTreeSnapshot) : toSnapshot(emptyTabTree(mothership, 0));
  };
  const invalid = (detail: string, tab_id: string | null = null): SaveResult => ({
    status: "invalid",
    reason: "tab_tree_invalid",
    tab_id,
    detail,
  });

  return {
    async load(projectId, mothership) {
      return current(projectId, mothership);
    },
    async save(projectId, mothership, snapshot) {
      const stored = current(projectId, mothership);
      if (snapshot.version !== stored.version) return { status: "conflict", reason: "version_stale", current: stored };
      const parsed = fromSnapshot(structuredClone(snapshot));
      if (!parsed.ok) return invalid(parsed.error.message);
      const tree = parsed.tree;
      if (tree.mothership !== mothership) return invalid(`tree is for ${tree.mothership}`);
      // rev 8.8: pruned_at is sent only on a tab being restored, one the
      // stored row holds as retired.
      for (const id of Object.keys(tree.nodes)) {
        if (tree.nodes[id].pruned_at === undefined) continue;
        const retired = stored.tree.history[id]?.node;
        const fields = ["pruned_at", "side", "kind", "ref", "branch_origin", "opened_by", "hier_number", "public_number"] as const;
        if (!retired || fields.some((field) => JSON.stringify(tree.nodes[id][field]) !== JSON.stringify(retired[field]))) return invalid(`restore differs from retired node ${id}`, id);
      }
      const hiers = mapFor(hierHolders, rowKey(projectId, mothership));
      const publics = mapFor(publicHolders, projectId);
      const issued = (nextPublic.get(projectId) ?? 1) - 1;
      const all = [
        ...Object.keys(tree.nodes).map((id) => tree.nodes[id]),
        ...Object.keys(tree.history).map((id) => tree.history[id].node),
      ];
      for (const n of all) {
        if (n.public_number !== null && n.public_number > issued) {
          return invalid(`public_number ${n.public_number} was never allocated`, n.tab_id);
        }
      }
      const clashes: string[] = [];
      let clashTab: string | null = null;
      for (const n of all) {
        const h = hiers.get(n.hier_number);
        if (h !== undefined && h !== n.tab_id) clashes.push(`hier_number ${n.hier_number} belongs to ${h}, not ${n.tab_id}`);
        if (n.public_number !== null) {
          const p = publics.get(n.public_number);
          if (p !== undefined && p !== n.tab_id) clashes.push(`public_number ${n.public_number} belongs to ${p}, not ${n.tab_id}`);
        }
        if (clashes.length > 0 && clashTab === null) clashTab = n.tab_id;
      }
      if (clashes.length > 0) {
        return { status: "conflict", reason: "number_conflict", tab_id: clashTab ?? undefined, detail: clashes.join("; "), current: stored };
      }
      for (const n of all) {
        hiers.set(n.hier_number, n.tab_id);
        if (n.public_number !== null) publics.set(n.public_number, n.tab_id);
      }
      // What the server does to the rows: a restore clears pruned_at; a new
      // pruned retirement records pruned_at = closed_at.
      const nodes: Record<string, TabNode> = {};
      for (const id of Object.keys(tree.nodes)) {
        const n = tree.nodes[id];
        if (n.pruned_at === undefined) nodes[id] = n;
        else {
          const cleared = { ...n };
          delete cleared.pruned_at;
          nodes[id] = cleared;
        }
      }
      const history: Record<string, ClosedTab> = {};
      for (const id of Object.keys(tree.history)) {
        const entry = tree.history[id];
        const known = Object.hasOwn(stored.tree.history, id);
        if (known || entry.close_mode !== "prune" || entry.node.pruned_at === entry.closed_at) history[id] = entry;
        else history[id] = { ...entry, node: { ...entry.node, pruned_at: entry.closed_at } };
      }
      const version = stored.version + 1;
      const accepted = toSnapshot({ ...tree, nodes, history, version });
      rows.set(rowKey(projectId, mothership), JSON.stringify(accepted));
      return { status: "saved", snapshot: structuredClone(accepted) };
    },
    async allocate(projectId, _mothership, tabId) {
      const byTab = mapFor<string, number>(allocated, projectId);
      const had = byTab.get(tabId);
      if (had !== undefined) return { public_number: had };
      const n = nextPublic.get(projectId) ?? 1;
      nextPublic.set(projectId, n + 1);
      byTab.set(tabId, n);
      return { public_number: n };
    },
    async retired() {
      return { entries: [], next_before: null };
    },
  };
}
