/**
 * contracts/adapters/preBackend.ts — the PRE-BACKEND feeder (SPR-06 M2).
 * LAZY module. Composes the registry projects (listProjects), the
 * investigation forest (listInvestigations + parent_investigation_id + the
 * per-owner local spawn map) and the companion tabs into a ContextTree, and
 * marks every node `provenance: "pre-backend"`.
 *
 * This file is the ONLY constructor of `source.kind: "investigation"` and
 * `scopeProvenance: "session-global"` (writerCensus.test.ts). The deletion
 * path (CONTRACTS.md §3): write adapters/backend.ts publishing a
 * `provenance: "backend"` tree through the same `publishTree`, replace the
 * one `<PreBackendTreeFeed />` mount line, delete this file and its test.
 *
 * The forest merge is self-contained (not hooks/useInvestigationTree):
 * two test files `vi.mock` that hook whole, and the hook drops cycle
 * members and freezes its local map at mount. Here a cycle promotes every
 * member to a forest root (no node is dropped) and the local map is re-read
 * per compose. The sidebar keeps its own behaviour.
 */
import { useEffect, useSyncExternalStore } from "react";

import { useInvestigationList } from "../../../hooks/useInvestigationList";
import { accountStorageKey, subscribeWorkspaceOwner, useWorkspaceOwner, workspaceOwnerSession } from "../../../lib/accountWorkspaceOwner";
import type { InvestigationSummary } from "../../../lib/api";
import { listProjects, type Project, type ProjectMember } from "../../../lib/api/projects";
import { useCompanion, type AgentTabDescriptor } from "../../companionStore";
import { TAB_PROJECT_ID } from "../../tabTreeStore";
import { AGENT_RUN_KIND_OF_TAB, agentViewId, type AgentNode, type AgentStatusRecord, type ContextTree, type ProjectNode, type RunDescriptor } from "../tree";
import { markTreeError, markTreeLoading, markTreeUnfed, publishTree } from "../treeStore";

export interface PreBackendInputs {
  /** listProjects(), archived excluded as the picker does. */
  projects: readonly Project[];
  /** useInvestigationList (limit 50, 30 s poll). */
  investigations: readonly InvestigationSummary[];
  /** Re-read PER COMPOSE from accountStorageKey("antiek:investigation_tree"), values filtered to strings. */
  localParents: Readonly<Record<string, string>>;
  /** useCompanion.getState().tabs. */
  companionTabs: readonly AgentTabDescriptor[];
  /** Optional; no production caller today. */
  membersByProject?: ReadonlyMap<string, readonly ProjectMember[]>;
}

const EMPTY_NODES: readonly ProjectNode[] = Object.freeze([]);
const EMPTY_AGENTS: readonly AgentNode[] = Object.freeze([]);
const PROVENANCE = "pre-backend" as const;

/** The sidebar's own storage key (hooks/useInvestigationTree.ts:6),
 *  duplicated so this module stays out of that hook's vi.mock graph. */
const LOCAL_TREE_KEY = "antiek:investigation_tree";

/** The per-owner spawn map, values filtered to strings. Re-read on every call. */
export function readLocalParents(): Readonly<Record<string, string>> {
  if (typeof window === "undefined") return {};
  const key = accountStorageKey(LOCAL_TREE_KEY);
  if (key === null) return {};
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "string" && v.trim()) out[k] = v.trim();
    }
    return out;
  } catch {
    return {};
  }
}

const since = (s: InvestigationSummary | null): string | undefined =>
  s ? (s.completed_at ?? s.started_at ?? undefined) : undefined;

function runOf(id: string, s: InvestigationSummary | null): RunDescriptor {
  const at = since(s);
  return {
    agentViewId: agentViewId("research-thread", id),
    ...(s ? { state: s.status } : {}),
    ...(at ? { since: at } : {}),
  };
}

function statusOf(s: InvestigationSummary): AgentStatusRecord {
  return { state: s.status, since: s.completed_at ?? s.started_at ?? null, lastSeen: null, freshness: "live", provenance: PROVENANCE };
}

/** The project each investigation is a member of, when exactly one. */
function memberProjects(members: PreBackendInputs["membersByProject"]): Map<string, string> {
  const out = new Map<string, string>();
  if (!members) return out;
  const seen = new Map<string, Set<string>>();
  for (const [projectId, rows] of members) {
    for (const m of rows) {
      if (m.member_kind !== "investigation") continue;
      const set = seen.get(m.member_id) ?? new Set<string>();
      set.add(projectId);
      seen.set(m.member_id, set);
    }
  }
  for (const [inv, projects] of seen) if (projects.size === 1) out.set(inv, [...projects][0]);
  return out;
}

const newestFirst = (a: InvestigationSummary, b: InvestigationSummary) =>
  (b.started_at ?? "").localeCompare(a.started_at ?? "");

/** Pure. Every node `provenance: "pre-backend"`; status "ready". */
export function composePreBackendTree(inputs: PreBackendInputs): ContextTree {
  const byId = new Map<string, InvestigationSummary>();
  for (const s of inputs.investigations) byId.set(s.investigation_id, s);

  // 1. Parent edges: substrate first, then the local spawn map.
  const parentOf = new Map<string, string | null>();
  for (const s of inputs.investigations) {
    const substrate = s.parent_investigation_id?.trim();
    const local = inputs.localParents[s.investigation_id]?.trim();
    parentOf.set(s.investigation_id, substrate || local || null);
  }

  // 2. Cycle detection: a node that reaches itself walking parents is on a
  //    cycle and becomes a forest root (no node is ever dropped).
  const onCycle = new Set<string>();
  for (const id of byId.keys()) {
    let cur = parentOf.get(id) ?? null;
    let steps = 0;
    while (cur !== null && byId.has(cur) && steps <= byId.size) {
      if (cur === id) { onCycle.add(id); break; }
      cur = parentOf.get(cur) ?? null;
      steps += 1;
    }
  }

  const childrenOf = new Map<string, InvestigationSummary[]>();
  const forestRoots: { summary: InvestigationSummary; parentMissing: boolean }[] = [];
  for (const s of inputs.investigations) {
    const id = s.investigation_id;
    const parent = parentOf.get(id) ?? null;
    if (parent === null || onCycle.has(id)) forestRoots.push({ summary: s, parentMissing: false });
    else if (!byId.has(parent)) forestRoots.push({ summary: s, parentMissing: true });
    else childrenOf.set(parent, [...(childrenOf.get(parent) ?? []), s]);
  }

  // 3. Agents from the companion tabs; filed by membership when linked.
  const memberOf = memberProjects(inputs.membersByProject);
  const registryIds = new Set(inputs.projects.map((p) => p.project_id));
  const agentsByOwner = new Map<string, AgentNode[]>();
  const crossProjectAgents: AgentNode[] = [];
  for (const t of inputs.companionTabs) {
    const investigationId = t.kind === "research-thread" ? t.investigationId?.trim() || undefined : undefined;
    const summary = investigationId ? byId.get(investigationId) ?? null : null;
    const project = investigationId ? memberOf.get(investigationId) : undefined;
    const linked = project !== undefined && registryIds.has(project);
    const owner = linked ? (summary ? investigationId! : project) : null;
    const base = {
      id: investigationId ?? t.id,
      viewId: t.id,
      viewOpen: true,
      kind: t.kind,
      runKind: AGENT_RUN_KIND_OF_TAB[t.kind],
      title: t.title,
      ...(investigationId ? { investigationId } : {}),
      ...(t.documentId ? { documentId: t.documentId } : {}),
      ...(summary ? { status: statusOf(summary) } : {}),
      provenance: PROVENANCE,
    };
    if (owner !== null) {
      const node: AgentNode = { ...base, scope: "project", scopeProvenance: "registry-member", projectId: owner };
      agentsByOwner.set(owner, [...(agentsByOwner.get(owner) ?? []), node]);
    } else {
      crossProjectAgents.push({ ...base, scope: "cross-project", scopeProvenance: "session-global", projectId: null });
    }
  }
  const agentsFor = (id: string): readonly AgentNode[] => agentsByOwner.get(id) ?? EMPTY_AGENTS;

  // 4. Sub-project nodes, newest-first at every level.
  const subproject = (s: InvestigationSummary, parentId: string, parentMissing: boolean): ProjectNode => {
    const id = s.investigation_id;
    const kids = [...(childrenOf.get(id) ?? [])].sort(newestFirst);
    return {
      id,
      kind: "subproject",
      title: s.question ?? id,
      parentId,
      children: kids.length ? kids.map((c) => subproject(c, id, false)) : EMPTY_NODES,
      agents: agentsFor(id),
      archived: false,
      provenance: PROVENANCE,
      source: { kind: "investigation", summary: s, parentMissing, run: runOf(id, s) },
    };
  };

  // 5. Roots: the default node, then the registry projects in server order.
  //    A forest root files under the default node unless membership links
  //    it to exactly one registry project.
  forestRoots.sort((a, b) => newestFirst(a.summary, b.summary));
  const rootsByProject = new Map<string, ProjectNode[]>();
  const file = (projectId: string, node: ProjectNode) =>
    rootsByProject.set(projectId, [...(rootsByProject.get(projectId) ?? []), node]);
  for (const r of forestRoots) {
    const target = memberOf.get(r.summary.investigation_id);
    const home = target !== undefined && registryIds.has(target) ? target : TAB_PROJECT_ID;
    file(home, subproject(r.summary, home, r.parentMissing));
  }

  const defaultNode: ProjectNode = {
    id: TAB_PROJECT_ID,
    kind: "project",
    title: "Default project",
    parentId: null,
    children: rootsByProject.get(TAB_PROJECT_ID) ?? EMPTY_NODES,
    agents: agentsFor(TAB_PROJECT_ID),
    archived: false,
    provenance: PROVENANCE,
    source: { kind: "default" },
  };
  const projects = inputs.projects.map((p): ProjectNode => ({
    id: p.project_id,
    kind: "project",
    title: p.title,
    parentId: null,
    children: rootsByProject.get(p.project_id) ?? EMPTY_NODES,
    agents: agentsFor(p.project_id),
    ...(inputs.membersByProject?.has(p.project_id) ? { members: inputs.membersByProject.get(p.project_id)! } : {}),
    memberCount: p.member_count,
    archived: p.archived_at !== null,
    provenance: PROVENANCE,
    source: { kind: "registry", project: p },
  }));

  return {
    roots: [defaultNode, ...projects],
    crossProjectAgents,
    provenance: PROVENANCE,
    status: "ready",
    error: null,
  };
}

// ---------------------------------------------------------------------------
// The registry cache: keyed by the owner epoch; a new epoch always refetches
// and never serves another owner's list.
// ---------------------------------------------------------------------------

interface RegistryCache {
  epoch: number;
  status: "idle" | "loading" | "ready" | "error";
  projects: readonly Project[];
  error: string | null;
}

let registry: RegistryCache = { epoch: -1, status: "idle", projects: [], error: null };
const registryListeners = new Set<() => void>();
const notifyRegistry = () => { for (const l of [...registryListeners]) l(); };
const subscribeRegistry = (l: () => void) => { registryListeners.add(l); return () => { registryListeners.delete(l); }; };
const readRegistry = () => registry;

function ensureRegistry(epoch: number): void {
  if (registry.epoch === epoch && registry.status !== "idle") return;
  registry = { epoch, status: "loading", projects: [], error: null };
  notifyRegistry();
  listProjects().then(
    (projects) => {
      if (workspaceOwnerSession().epoch !== epoch) return;
      registry = { epoch, status: "ready", projects, error: null };
      notifyRegistry();
    },
    (e: unknown) => {
      if (workspaceOwnerSession().epoch !== epoch) return;
      registry = { epoch, status: "error", projects: [], error: e instanceof Error ? e.message : String(e) };
      notifyRegistry();
    },
  );
}

// An owner change empties the tree at once: the next compose under the new
// epoch republishes. (The registry refetches by epoch; nothing here calls
// setWorkspaceOwner.)
let mounts = 0;
subscribeWorkspaceOwner(() => {
  if (mounts > 0) markTreeUnfed();
});

/** Refcounted feeder. Mount once near the consumer root (SPR-04). First
 *  mount → markTreeLoading; each input identity change → publishTree; last
 *  unmount → markTreeUnfed. */
export function usePreBackendTreeFeed(opts?: { investigationLimit?: number }): void {
  const owner = useWorkspaceOwner();
  const reg = useSyncExternalStore(subscribeRegistry, readRegistry, readRegistry);
  const { investigations, error: investigationError } = useInvestigationList({ limit: opts?.investigationLimit });
  const tabs = useCompanion((s) => s.tabs);

  useEffect(() => {
    mounts += 1;
    if (mounts === 1) markTreeLoading();
    return () => {
      mounts -= 1;
      if (mounts === 0) markTreeUnfed();
    };
  }, []);

  useEffect(() => {
    ensureRegistry(owner.epoch);
  }, [owner.epoch]);

  useEffect(() => {
    if (reg.epoch !== owner.epoch || reg.status === "idle" || reg.status === "loading") {
      markTreeLoading();
      return;
    }
    if (reg.status === "error") {
      markTreeError(reg.error ?? "projects: unknown error");
      return;
    }
    publishTree(
      composePreBackendTree({ projects: reg.projects, investigations, localParents: readLocalParents(), companionTabs: tabs }),
      new Date().toISOString(),
    );
    if (investigationError) markTreeError(investigationError);
  }, [owner.epoch, reg, investigations, investigationError, tabs]);
}

export function PreBackendTreeFeed(props: { investigationLimit?: number }): null {
  usePreBackendTreeFeed(props);
  return null;
}
