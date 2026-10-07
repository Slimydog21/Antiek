/**
 * switcherFixtures.test.helpers.ts — the seeded generator the SPR-04 model
 * and reducer property tests share (not a test file: vitest collects
 * `*.test.ts`, not `*.test.helpers.ts`; excluded from the census scans by
 * its `.test.` infix). Every tree comes out of the REAL pre-backend
 * adapter (`composePreBackendTree`) over raw wire rows, never from a
 * hand-written node literal, so no generated tree can be one the adapter
 * refuses. A seeded LCG stands in for fast-check (not in package-lock).
 */
import type { ProjectMember } from "../../lib/api/projects";
import type { AgentTabDescriptor } from "../companionStore";
import { composePreBackendTree, type PreBackendInputs } from "../contracts/adapters/preBackend";
import { project, summary, tab } from "../contracts/fixtures.test.helpers";
import { isSelectionPathOf, type Selection } from "../contracts/selection";
import { checkTree, findAgent, type AgentNode, type ContextTree, type ProjectNode } from "../contracts/tree";

/** Numerical Recipes LCG; deterministic per seed. */
export function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

const STATUSES = ["completed", "in_progress", "failed", "stopped"] as const;

/** 0-4 projects, 0-12 investigations with random parents (self, 2-cycle,
 *  outside the list, none), 0-5 companion tabs (dialogue, known and unknown
 *  threads; deduped by id as the companion store is), random members. */
export function genInputs(seed: number): PreBackendInputs {
  const rnd = lcg(seed);
  const int = (n: number) => Math.floor(rnd() * n);
  const projects = Array.from({ length: int(5) }, (_, i) => project(`p${i + 1}`, `Project ${i + 1}`, { order: i + 1 }));
  const ids = Array.from({ length: int(13) }, (_, i) => `inv-${i + 1}`);
  const investigations = ids.map((id, i) => {
    const r = rnd();
    let parent: string | null = null;
    if (r < 0.35) parent = null;
    else if (r < 0.7) parent = ids[int(ids.length)];
    else if (r < 0.8) parent = "inv-outside";
    else parent = ids[(i + 1) % ids.length];
    const day = String(1 + int(28)).padStart(2, "0");
    const status = STATUSES[int(STATUSES.length)];
    return summary(id, {
      parent_investigation_id: parent,
      started_at: `2026-09-${day}T10:00:00Z`,
      status,
      completed_at: status === "in_progress" ? null : `2026-09-${day}T11:00:00Z`,
    });
  });
  const seen = new Set<string>();
  const companionTabs: AgentTabDescriptor[] = [];
  const nTabs = int(6);
  for (let k = 0; k < nTabs; k += 1) {
    const r = rnd();
    const t = r < 0.2
      ? tab("dialogue")
      : (() => {
        const inv = r < 0.85 && ids.length ? ids[int(ids.length)] : `inv-unknown-${int(3)}`;
        return tab("research-thread", { investigationId: inv, title: `thread ${inv}` });
      })();
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    companionTabs.push(t);
  }
  const membersByProject = new Map<string, readonly ProjectMember[]>();
  for (const p of projects) {
    if (rnd() < 0.5) continue;
    const rows: ProjectMember[] = [];
    const nRows = int(4);
    for (let k = 0; k < nRows; k += 1) {
      const inv = ids.length && rnd() < 0.8 ? ids[int(ids.length)] : `inv-outside-${int(2)}`;
      rows.push({ member_kind: "investigation", member_id: inv, added_at: "2026-09-18T10:00:00Z" });
    }
    membersByProject.set(p.project_id, rows);
  }
  return {
    projects,
    investigations,
    localParents: {},
    companionTabs,
    ...(membersByProject.size ? { membersByProject } : {}),
  };
}

export function genTree(seed: number): ContextTree {
  const tree = composePreBackendTree(genInputs(seed));
  const problems = checkTree(tree);
  if (problems.length) throw new Error(`seed ${seed}: the adapter produced an unsound tree: ${problems.join("; ")}`);
  return tree;
}

export function allNodes(tree: ContextTree): ProjectNode[] {
  const out: ProjectNode[] = [];
  const walk = (n: ProjectNode) => { out.push(n); n.children.forEach(walk); };
  tree.roots.forEach(walk);
  return out;
}

export function allAgents(tree: ContextTree): AgentNode[] {
  return [...allNodes(tree).flatMap((n) => [...n.agents]), ...tree.crossProjectAgents];
}

/** Every valid selection (each node, each node with every agent the
 *  contract admits there) plus stale ones. */
export function selectionsFor(tree: ContextTree): { valid: Selection[]; stale: Selection[] } {
  const valid: Selection[] = [];
  const nodes = allNodes(tree);
  const agents = allAgents(tree);
  const rootOf = (n: ProjectNode): string => {
    let cur = n;
    const byId = new Map(nodes.map((x) => [x.id, x]));
    while (cur.parentId !== null) cur = byId.get(cur.parentId)!;
    return cur.id;
  };
  for (const n of nodes) {
    const base: Selection = n.parentId === null ? { projectId: n.id } : { projectId: rootOf(n), subProjectId: n.id };
    valid.push(base);
    for (const a of agents) {
      const withAgent = { ...base, agentId: a.id };
      if (isSelectionPathOf(withAgent, tree) && findAgent(tree, a.id)) valid.push(withAgent);
    }
  }
  const stale: Selection[] = [{ projectId: "ghost" }];
  if (tree.roots.length) stale.push({ projectId: tree.roots[0].id, subProjectId: "ghost" });
  const sub = nodes.find((n) => n.parentId !== null);
  if (sub) stale.push({ projectId: sub.id });
  if (sub && tree.roots.length > 1) {
    const other = tree.roots.find((r) => r.id !== rootOf(sub));
    if (other) stale.push({ projectId: other.id, subProjectId: sub.id });
  }
  return { valid, stale };
}

export function deepFreeze<T>(v: T): T {
  if (v && typeof v === "object" && !Object.isFrozen(v)) {
    Object.freeze(v);
    for (const k of Object.keys(v as object)) deepFreeze((v as Record<string, unknown>)[k]);
  }
  return v;
}

export const SEEDS = Array.from({ length: 200 }, (_, i) => i + 1);
