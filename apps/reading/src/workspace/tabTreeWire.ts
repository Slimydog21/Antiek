/**
 * tabTreeWire.ts — the model (tabTree.ts) ↔ THREAD-CONTRACT §1.6 wire
 * mapping for lane B's GET/PUT /projects/{id}/tabs/{mothership}.
 *
 * Pure, like the model. What it maps:
 *  - Branch origin kinds: the UI's `island` is the wire's `selection` (§1.0).
 *  - `history` ↔ `retired[]`. The client's closed tabs are NOT sent in the
 *    PUT body: the server finds them by diff and holds them as
 *    `{closed_at, close_mode, node}` rows. `fromWire` rebuilds `history`
 *    from `retired[]`; `toWireSnapshot` writes it back out newest first.
 *  - `next_root_index` ↔ `next_child_index["root"]`. Counters are never sent
 *    in the PUT: the server maintains them (§1.6 rev 6).
 *  - `active: {left, right}`. Left is the focused tab when it is a left tab;
 *    right is the focused tab when it is a right tab, else the server's
 *    `active.right`, held unchanged until agent tabs move into the tree (A14).
 *  - A node carries only the Part 2 §2.2 fields, built field by field, so no
 *    model-only field can reach the server (which refuses any other field).
 *
 * `pruned_at` passes through untouched both ways: the server sets it on a
 * pruned retirement, a restore sends it back, and the server clears it
 * (rev 8.8). This module never adds or strips it.
 */
import type {
  ActiveBySide,
  BranchOrigin as WireOrigin,
  PutTabsRequest,
  RetiredEntry,
  TabNode as WireNode,
  TabsSnapshot,
} from "../lib/api/projectTabs";
import {
  fromWireKind,
  toWireKind,
  type ClosedTab,
  type Mothership,
  type TabNode,
  type TabTree,
} from "./tabTree";

/** The key the server counts root tabs under (§1.6 rev 6). */
export const ROOT_COUNTER_KEY = "root";

export interface ToWireOptions {
  /** The title the surface currently holds for a node (null = unknown, keep
   *  the node's own). Titles live in the tabTitles cache, not the model. */
  titleOf?: (node: TabNode) => string | null;
}

// ---------------------------------------------------------------------------
// Nodes
// ---------------------------------------------------------------------------

function nodeToWire(n: TabNode, opts: ToWireOptions = {}): WireNode {
  const title = opts.titleOf?.(n) ?? n.title;
  const out: WireNode = {
    tab_id: n.tab_id,
    parent_tab_id: n.parent_tab_id,
    side: n.side,
    kind: n.kind,
    ref: n.ref,
    title,
    mothership: n.mothership,
    public_number: n.public_number,
    hier_number: n.hier_number,
    child_order: [...n.child_order],
  };
  if (n.pane !== undefined) out.pane = { ...n.pane };
  if (n.branch_origin !== undefined) {
    out.branch_origin = { ...n.branch_origin, kind: toWireKind(n.branch_origin.kind) } as WireOrigin;
  }
  if (n.opened_by !== undefined) out.opened_by = { ...n.opened_by };
  if (n.last_visited_child_id !== undefined) out.last_visited_child_id = n.last_visited_child_id;
  if (n.pruned_at !== undefined) out.pruned_at = n.pruned_at;
  return out;
}

/** The wire allows null on optional fields; the model keeps them absent. */
function nodeFromWire(w: WireNode): TabNode {
  const out: TabNode = {
    tab_id: w.tab_id,
    parent_tab_id: w.parent_tab_id,
    side: w.side,
    kind: w.kind,
    ref: w.ref,
    title: w.title,
    mothership: w.mothership,
    public_number: w.public_number,
    hier_number: w.hier_number,
    child_order: [...w.child_order],
  };
  if (w.pane != null) out.pane = { ...w.pane } as TabNode["pane"];
  if (w.branch_origin != null) {
    out.branch_origin = { ...w.branch_origin, kind: fromWireKind(w.branch_origin.kind) } as TabNode["branch_origin"];
  }
  if (w.opened_by != null) out.opened_by = { ...w.opened_by };
  if (w.last_visited_child_id != null) out.last_visited_child_id = w.last_visited_child_id;
  if (w.pruned_at != null) out.pruned_at = w.pruned_at;
  return out;
}

// ---------------------------------------------------------------------------
// Retirements ↔ history
// ---------------------------------------------------------------------------

/**
 * Rebuild `history` from `retired[]` (newest first). The server holds one
 * unrestored row per tab; an open tab or a second row for the same tab_id
 * (an older close) is skipped.
 *
 * `close_id` is client-only. A pruned subtree is one close: the server
 * writes one row per node, each with its own `closed_at` (consecutive
 * microseconds, §1.6 rev 8.6), so rows are grouped by structure instead: a
 * `prune` row whose parent's row is also `prune` and lists it in its
 * `child_order` went with that parent. The group's id names its head.
 */
export function historyFromRetired(
  retired: readonly RetiredEntry[],
  open: Readonly<Record<string, unknown>>,
): Record<string, ClosedTab> {
  const rows = new Map<string, RetiredEntry>();
  for (const entry of retired) {
    const id = entry.node.tab_id;
    if (Object.hasOwn(open, id) || rows.has(id)) continue;
    rows.set(id, entry);
  }
  const wentWithParent = (entry: RetiredEntry): RetiredEntry | null => {
    const parentId = entry.node.parent_tab_id;
    if (entry.close_mode !== "prune" || parentId === null) return null;
    const parent = rows.get(parentId);
    if (!parent || parent.close_mode !== "prune" || !parent.node.child_order.includes(entry.node.tab_id)) return null;
    return parent;
  };
  const history: Record<string, ClosedTab> = {};
  for (const [id, entry] of rows) {
    let head = entry;
    const seen = new Set<string>([id]);
    for (let up = wentWithParent(head); up !== null && !seen.has(up.node.tab_id); up = wentWithParent(head)) {
      seen.add(up.node.tab_id);
      head = up;
    }
    history[id] = {
      node: nodeFromWire(entry.node),
      close_id: `${head.node.tab_id}@${head.closed_at}`,
      closed_at: entry.closed_at,
      close_mode: entry.close_mode,
    };
  }
  return history;
}

/** `history` as the server's `retired[]`, newest first. */
export function retiredFromHistory(tree: TabTree): RetiredEntry[] {
  const entries = Object.keys(tree.history).map((id) => tree.history[id]);
  // Stable: equal closed_at keeps the history's own order.
  const sorted = entries
    .map((entry, i) => ({ entry, i }))
    .sort((a, b) => (a.entry.closed_at < b.entry.closed_at ? 1 : a.entry.closed_at > b.entry.closed_at ? -1 : a.i - b.i));
  return sorted.map(({ entry }) => ({
    closed_at: entry.closed_at,
    close_mode: entry.close_mode,
    node: nodeToWire(entry.node),
  }));
}

// ---------------------------------------------------------------------------
// Whole trees
// ---------------------------------------------------------------------------

function activeToWire(tree: TabTree): ActiveBySide {
  const focused = tree.active_tab_id !== null && Object.hasOwn(tree.nodes, tree.active_tab_id) ? tree.nodes[tree.active_tab_id] : null;
  return {
    left: focused?.side === "left" ? focused.tab_id : null,
    right: focused?.side === "right" ? focused.tab_id : tree.active_right,
  };
}

function treeToWire(tree: TabTree, opts: ToWireOptions): PutTabsRequest["tree"] {
  const nodes: Record<string, WireNode> = {};
  for (const id of Object.keys(tree.nodes)) nodes[id] = nodeToWire(tree.nodes[id], opts);
  return { nodes, root_order: [...tree.root_order] };
}

/** The PUT body: the open tree, both panes' active tabs, and the version the
 *  tree descends from. No history and no counters (the server holds both). */
export function toWire(tree: TabTree, opts: ToWireOptions = {}): PutTabsRequest {
  return { tree: treeToWire(tree, opts), active: activeToWire(tree), expected_version: tree.version };
}

/** The tree in the GET shape: what the server would answer for it. Used to
 *  prove the round trip and by tests; the PUT sends `toWire`. */
export function toWireSnapshot(tree: TabTree, opts: ToWireOptions = {}): TabsSnapshot {
  const next_child_index: Record<string, number> = {};
  if (tree.next_root_index !== 1) next_child_index[ROOT_COUNTER_KEY] = tree.next_root_index;
  for (const id of Object.keys(tree.next_child_index)) next_child_index[id] = tree.next_child_index[id];
  return {
    tree: treeToWire(tree, opts),
    active: activeToWire(tree),
    version: tree.version,
    next_child_index,
    retired: retiredFromHistory(tree),
  };
}

/**
 * The server's snapshot as a model tree. `mothership` is the route's: the
 * snapshot does not name it, and an empty tree has no node to read it from.
 * The server has validated the structure (§1.6 structural checks); the
 * boundary parse is lane B's `parseTabsSnapshot`.
 */
export function fromWire(snapshot: TabsSnapshot, mothership: Mothership): TabTree {
  const nodes: Record<string, TabNode> = {};
  for (const id of Object.keys(snapshot.tree.nodes)) nodes[id] = nodeFromWire(snapshot.tree.nodes[id]);
  const next_child_index: Record<string, number> = {};
  let next_root_index = 1;
  for (const key of Object.keys(snapshot.next_child_index)) {
    if (key === ROOT_COUNTER_KEY) next_root_index = snapshot.next_child_index[key];
    else next_child_index[key] = snapshot.next_child_index[key];
  }
  return {
    mothership,
    nodes,
    root_order: [...snapshot.tree.root_order],
    active_tab_id: snapshot.active.left,
    active_right: snapshot.active.right,
    history: historyFromRetired(snapshot.retired, nodes),
    next_root_index,
    next_child_index,
    version: snapshot.version,
  };
}
