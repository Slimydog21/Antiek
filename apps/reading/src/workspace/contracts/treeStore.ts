/**
 * contracts/treeStore.ts — the provenance-neutral tree store (SPR-06).
 * LAZY module (imports selection → tabTreeStore).
 *
 * Any feeder (adapters/preBackend.ts today; adapters/backend.ts under
 * SPR-B) publishes through `publishTree`, the ONLY write path. The store
 * reuses node identities from the previous tree by fingerprint, so a
 * consumer holding a node reference re-renders only when that node (or a
 * descendant) changed, and returns the previous tree by reference when
 * nothing changed so selector subscribers do not notify. `composedAt`
 * lives OUTSIDE the tree so identity reuse holds across polls.
 */
import { create } from "zustand";
import { useStoreWithEqualityFn } from "zustand/traditional";

import { useSelection } from "./selection";
import { checkTree, findAgent, findProjectPath, type AgentNode, type ContextTree, type ProjectNode } from "./tree";

const EMPTY_ROOTS: readonly ProjectNode[] = Object.freeze([]);
const EMPTY_AGENTS: readonly AgentNode[] = Object.freeze([]);

export const EMPTY_TREE: ContextTree = Object.freeze({
  roots: EMPTY_ROOTS,
  crossProjectAgents: EMPTY_AGENTS,
  provenance: "pre-backend",
  status: "unfed",
  error: null,
});

interface TreeStoreState {
  tree: ContextTree;
  composedAt: string | null;
}

export const useContextTreeStore = create<TreeStoreState>()(() => ({ tree: EMPTY_TREE, composedAt: null }));

// ---------------------------------------------------------------------------
// Fingerprints (no `seq`, no `activeTabId`: a view reorder is not a change)
// ---------------------------------------------------------------------------

const fingerprints = new WeakMap<object, string>();

function agentFingerprint(a: AgentNode): string {
  return [
    a.id, a.viewId, a.viewOpen ? 1 : 0, a.kind, a.scope, a.scopeProvenance, a.projectId ?? "",
    a.investigationId ?? "", a.documentId ?? "", a.title, a.runId ?? "",
    a.status?.state ?? "", a.status?.since ?? "", a.status?.freshness ?? "", a.provenance,
  ].join("\u0000");
}

function projectFingerprint(n: ProjectNode): string {
  const ids = (xs: readonly { id: string }[]) => xs.map((x) => x.id).join(",");
  const base = [n.id, n.kind, n.title, n.archived ? 1 : 0, n.parentId ?? "", n.provenance];
  if (n.source.kind === "investigation") {
    const s = n.source.summary;
    base.push("investigation", n.source.parentMissing ? 1 : 0, s?.status ?? "", s?.question ?? "", s?.completed_at ?? "",
      s?.started_at ?? "", n.source.run.agentViewId, n.source.run.state ?? "", n.source.run.since ?? "");
  } else if (n.source.kind === "registry") {
    base.push("registry", n.memberCount ?? "", n.members ? n.members.map((m) => `${m.member_kind}:${m.member_id}`).join(",") : "-",
      n.source.project.updated_at ?? "", n.source.project.title, n.source.project.kind, n.source.project.pinned ? 1 : 0);
  } else {
    base.push("default");
  }
  base.push(ids(n.children), ids(n.agents));
  return base.join("\u0000");
}

/** Exported for tests. Cached per object. */
export function fingerprintOf(n: ProjectNode | AgentNode): string {
  const hit = fingerprints.get(n);
  if (hit !== undefined) return hit;
  const fp = "viewId" in n ? agentFingerprint(n) : projectFingerprint(n);
  fingerprints.set(n, fp);
  return fp;
}

interface PrevIndex {
  nodes: Map<string, ProjectNode>;
  agents: Map<string, AgentNode>;
}

function indexTree(tree: ContextTree): PrevIndex {
  const nodes = new Map<string, ProjectNode>();
  const agents = new Map<string, AgentNode>();
  const walk = (n: ProjectNode) => {
    nodes.set(n.id, n);
    for (const a of n.agents) agents.set(a.id, a);
    n.children.forEach(walk);
  };
  tree.roots.forEach(walk);
  for (const a of tree.crossProjectAgents) agents.set(`cross:${a.id}`, a);
  return { nodes, agents };
}

function reuseAgent(a: AgentNode, prev: AgentNode | undefined): AgentNode {
  return prev && fingerprintOf(prev) === fingerprintOf(a) ? prev : a;
}

function reuseList<T>(next: readonly T[], prevList: readonly T[], map: (x: T) => T): readonly T[] {
  const out = next.map(map);
  if (out.length === prevList.length && out.every((x, i) => x === prevList[i])) return prevList;
  if (out.every((x, i) => x === next[i])) return next;
  return out;
}

function reuseNode(n: ProjectNode, prev: PrevIndex): ProjectNode {
  const old = prev.nodes.get(n.id);
  const children = reuseList(n.children, old?.children ?? EMPTY_ROOTS, (c) => reuseNode(c, prev));
  const agents = reuseList(n.agents, old?.agents ?? EMPTY_AGENTS, (a) => reuseAgent(a, prev.agents.get(a.id)));
  if (old && fingerprintOf(old) === fingerprintOf(n) && children === old.children && agents === old.agents) return old;
  if (children === n.children && agents === n.agents) return n;
  return { ...n, children, agents };
}

function reuseTree(next: ContextTree, prevTree: ContextTree): ContextTree {
  const prev = indexTree(prevTree);
  const roots = reuseList(next.roots, prevTree.roots, (r) => reuseNode(r, prev));
  const cross = reuseList(next.crossProjectAgents, prevTree.crossProjectAgents, (a) => reuseAgent(a, prev.agents.get(`cross:${a.id}`)));
  if (roots === prevTree.roots && cross === prevTree.crossProjectAgents && next.status === prevTree.status &&
    next.error === prevTree.error && next.provenance === prevTree.provenance) return prevTree;
  if (roots === next.roots && cross === next.crossProjectAgents) return next;
  return { ...next, roots, crossProjectAgents: cross };
}

// ---------------------------------------------------------------------------
// The write path
// ---------------------------------------------------------------------------

/** The ONLY write path for any feeder. Runs `checkTree` first: a tree that
 *  fails it is REFUSED (the previous roots, agents and `composedAt` stay;
 *  status "error" names every violation), so the provenance rule
 *  (CONTRACTS.md §2) holds on the write path and not only in tests; a
 *  future feeder that flips a pre-backend node's provenance cannot reach
 *  `displayKind`. Otherwise reuses node identities by fingerprint; returns
 *  the previous tree by reference when nothing changed (the store then
 *  notifies only `composedAt` subscribers). Then reconciles the selection
 *  against the published tree. */
export function publishTree(next: ContextTree, composedAt: string): void {
  const problems = checkTree(next);
  if (problems.length > 0) {
    markTreeError(`publishTree refused: ${problems.join("; ")}`);
    return;
  }
  const prevTree = useContextTreeStore.getState().tree;
  const tree = reuseTree(next, prevTree);
  useContextTreeStore.setState(tree === prevTree ? { composedAt } : { tree, composedAt });
  useSelection.getState().reconcile(tree);
}

/** status "loading", roots kept. */
export function markTreeLoading(): void {
  const t = useContextTreeStore.getState().tree;
  if (t.status === "loading") return;
  useContextTreeStore.setState({ tree: { ...t, status: "loading" } });
}

export function markTreeError(message: string): void {
  const t = useContextTreeStore.getState().tree;
  if (t.status === "error" && t.error === message) return;
  useContextTreeStore.setState({ tree: { ...t, status: "error", error: message } });
}

/** The last feeder unmounted: back to the honest empty state. */
export function markTreeUnfed(): void {
  useContextTreeStore.setState({ tree: EMPTY_TREE, composedAt: null });
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useContextTree(): ContextTree;
export function useContextTree<T>(selector: (t: ContextTree) => T, equals?: (a: T, b: T) => boolean): T;
export function useContextTree<T>(selector?: (t: ContextTree) => T, equals?: (a: T, b: T) => boolean): T | ContextTree {
  return useStoreWithEqualityFn(
    useContextTreeStore,
    (s) => (selector ? selector(s.tree) : s.tree),
    equals as ((a: T | ContextTree, b: T | ContextTree) => boolean) | undefined,
  );
}

/** Identity-stable: the same node object until it (or a descendant) changes. */
export function useProjectNode(id: string): ProjectNode | null {
  return useContextTreeStore((s) => findProjectPath(s.tree, id)?.at(-1) ?? null);
}

/** By AgentNode.id (the run id). */
export function useAgentNode(id: string): AgentNode | null {
  return useContextTreeStore((s) => findAgent(s.tree, id)?.node ?? null);
}

/** The deepest selected node; null for a stale persisted id. */
export function useSelectedProjectNode(): ProjectNode | null {
  const target = useSelection((s) => s.selection.subProjectId ?? s.selection.projectId);
  return useContextTreeStore((s) => findProjectPath(s.tree, target)?.at(-1) ?? null);
}
