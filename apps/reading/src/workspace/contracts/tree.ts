/**
 * contracts/tree.ts — the typed project → sub-project → agent tree every
 * other sprint consumes (SPR-06 M1). ENTRY-SAFE: `import type` only; the
 * value graph of this module is empty, so the entry chunk may import it.
 *
 * Two identities, kept apart on purpose:
 *   - VIEW identity (`AgentNode.viewId`): the companion tab id
 *     (companionStore.agentTabId), a session-scoped view that the backend
 *     never persists;
 *   - RUN identity (`AgentNode.id`): the investigation id for a research
 *     thread; for the one-shot dialogue agent (no run exists) view and run
 *     collapse by construction and `id === viewId`.
 *
 * Provenance is on every node. A consumer may render "Sub-project" copy
 * ONLY for `provenance: "backend"`; a pre-backend sub-project is an
 * investigation wearing a costume, and `displayKind` is the only sanctioned
 * label source (rigor #1, the provenance-leak lens).
 *
 * Backend mapping (SPR-B, ffx-nav-backend-context / -agent-bridge) is in
 * CONTRACTS.md; every SPR-B cell there is unconfirmed as of
 * 2026-10-07T20:20Z and nothing here invents a value for it.
 */
import type { InvestigationSummary } from "../../lib/api";
import type { Project, ProjectMember } from "../../lib/api/projects";
import type { AgentTabKind } from "../companionStore";

/** Who asserted the node. A consumer may render "Sub-project" copy ONLY for "backend" (rigor #1). */
export type Provenance = "pre-backend" | "backend";
export type ProjectNodeKind = "project" | "subproject";

/** §2.2 opened_by.agent_kind, the RUN vocabulary (crossPane.ts:28-30). */
export type AgentKind = "research" | "dialogue" | "reformat" | "diligence" | "island";

/** VIEW → RUN vocabulary. A Record keyed by the union: adding an AgentTabKind
 *  without a row here fails tsc, and T5 checks it against companionRegistry
 *  at runtime (the registry is a lazy module; this one must not import it). */
export const AGENT_RUN_KIND_OF_TAB: Readonly<Record<AgentTabKind, AgentKind>> = Object.freeze({
  "research-thread": "research",
  dialogue: "dialogue",
});

/** Today's real run states: InvestigationSummary.status. SPR-B's "five
 *  states" are TODO(ffx-nav-backend-agent-bridge): unconfirmed, INBOX note
 *  pending. Not invented. */
export type AgentRunState = InvestigationSummary["status"];

/** Computed for EVERY investigation node, tab open or not, so the switcher
 *  can offer "focus" (view open) vs "open" (no view) and show a run state. */
export interface RunDescriptor {
  /** = agentViewId("research-thread", investigation_id). */
  agentViewId: string;
  /** summary.status; absent when the summary is null (outside the list window). Never defaulted. */
  state?: AgentRunState;
  /** completed_at ?? started_at; absent when neither exists. */
  since?: string;
}

export type ProjectNodeSource =
  /** backend: a write_folders row (lib/api/projects.ts Project, THREAD-CONTRACT §1.5). */
  | { kind: "registry"; project: Project }
  /** tabTreeStore.TAB_PROJECT_ID. backend: TODO(ffx-nav-backend-context) whether "default" survives server-side. */
  | { kind: "default" }
  /** PRE-BACKEND ONLY: an investigation wearing a sub-project costume.
   *  summary null = id known from a parent edge but outside the
   *  listInvestigations window (the adapter never builds one today; the
   *  shape stays so a feeder may). parentMissing = its parent is not in the
   *  list, so it was promoted to a forest root (depth is NOT identity). */
  | { kind: "investigation"; summary: InvestigationSummary | null; parentMissing: boolean; run: RunDescriptor };

export interface ProjectNode {
  /** Raw: Project.project_id | "default" | investigation_id. Never prefixed. */
  id: string;
  kind: ProjectNodeKind;
  /** backend: Project.title; pre-backend subproject: summary?.question ?? investigation_id. */
  title: string;
  /** backend: nested parent id (if SPR-B picks nested projects) or
   *  parent_investigation_id. Root: null. kind "subproject" ⇒ non-null. */
  parentId: string | null;
  children: readonly ProjectNode[];
  /** Agents with scope "project" filed here. Never a cross-project agent. */
  agents: readonly AgentNode[];
  /** backend: ProjectDetail.members. Absent = not fetched, NOT "no members". */
  members?: readonly ProjectMember[];
  /** backend: Project.member_count. Absent for default and subprojects. */
  memberCount?: number;
  /** backend: Project.archived_at !== null. Pre-backend subproject: always
   *  false, never derived from status. */
  archived: boolean;
  provenance: Provenance;
  source: ProjectNodeSource;
}

export type AgentScope = "project" | "cross-project";
/** How scope was decided. "session-global": the companion store has no
 *  project field (STAGED T9/P1-5), so the agent is honestly cross-project.
 *  "registry-member": linked via membersByProject. "backend": SPR-B said so,
 *  which only an agent with `provenance: "backend"` may claim (checkTree). */
export type ScopeProvenance = "session-global" | "registry-member" | "backend";

/** backend: agent-bridge status record. Absent status is representable and
 *  never defaulted to idle. */
export interface AgentStatusRecord {
  state: AgentRunState;
  /** backend `since`; pre-backend completed_at ?? started_at. */
  since: string | null;
  /** backend lastSeen; pre-backend null (useSeenVersion is a sidebar concern). */
  lastSeen: string | null;
  /** "stale": older than the 30 s poll or from a summary outside the window. */
  freshness: "live" | "stale";
  /** "backend" only under an agent with `provenance: "backend"` (checkTree). */
  provenance: Provenance;
}

export interface AgentNode {
  /** RUN/agent identity: investigation_id for research-thread; equals viewId
   *  for the one-shot dialogue agent (no run exists). */
  id: string;
  /** VIEW identity: the verbatim companion tab id (companionStore.ts:89-94).
   *  Never persisted by the backend. */
  viewId: string;
  viewOpen: boolean;
  /** backend: bridge run/attempt id. Pre-backend: ALWAYS absent, never
   *  fabricated (checkTree rejects a pre-backend agent carrying one). */
  runId?: string;
  /** VIEW vocabulary. */
  kind: AgentTabKind;
  /** RUN vocabulary = AGENT_RUN_KIND_OF_TAB[kind]. */
  runKind: AgentKind;
  scope: AgentScope;
  scopeProvenance: ScopeProvenance;
  /** Owning ProjectNode.id iff scope === "project"; null iff scope === "cross-project". */
  projectId: string | null;
  /** InvestigationSummary.investigation_id; absent for dialogue. */
  investigationId?: string;
  /** AgentTabDescriptor.documentId (the sourceDocumentOf rule), never guessed. */
  documentId?: string;
  title: string;
  status?: AgentStatusRecord;
  provenance: Provenance;
}

export type TreeStatus = "unfed" | "loading" | "ready" | "error";

export interface ContextTree {
  roots: readonly ProjectNode[];
  /** The ONLY home of scope "cross-project" agents. */
  crossProjectAgents: readonly AgentNode[];
  provenance: Provenance;
  /** "unfed": no feeder mounted; distinguishes "not fetched" from "empty". */
  status: TreeStatus;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Pure helpers (no store imports)
// ---------------------------------------------------------------------------

/** Reproduces companionStore.agentTabId without importing the store. T2
 *  proves the two agree. */
export function agentViewId(kind: AgentTabKind, investigationId?: string): string {
  if (kind === "research-thread") return `agent:thread:${investigationId ?? ""}`;
  return "agent:dialogue";
}

export function agentKindOfTab(kind: AgentTabKind): AgentKind {
  return AGENT_RUN_KIND_OF_TAB[kind];
}

/** The only sanctioned label source. Never "Sub-project" for pre-backend provenance. */
export function displayKind(n: ProjectNode): "Project" | "Default project" | "Investigation" | "Sub-project" {
  if (n.source.kind === "default") return "Default project";
  if (n.kind === "project") return "Project";
  if (n.provenance === "backend") return "Sub-project";
  return "Investigation";
}

/** root..node, or null when the id is not in the forest. */
export function findProjectPath(tree: ContextTree, nodeId: string): ProjectNode[] | null {
  const walk = (n: ProjectNode, path: ProjectNode[]): ProjectNode[] | null => {
    const here = [...path, n];
    if (n.id === nodeId) return here;
    for (const c of n.children) {
      const hit = walk(c, here);
      if (hit) return hit;
    }
    return null;
  };
  for (const r of tree.roots) {
    const hit = walk(r, []);
    if (hit) return hit;
  }
  return null;
}

/** By AgentNode.id (the RUN identity). owner is null for a cross-project agent. */
export function findAgent(tree: ContextTree, agentId: string): { node: AgentNode; owner: ProjectNode | null } | null {
  const walk = (n: ProjectNode): { node: AgentNode; owner: ProjectNode | null } | null => {
    const own = n.agents.find((a) => a.id === agentId);
    if (own) return { node: own, owner: n };
    for (const c of n.children) {
      const hit = walk(c);
      if (hit) return hit;
    }
    return null;
  };
  for (const r of tree.roots) {
    const hit = walk(r);
    if (hit) return hit;
  }
  const cross = tree.crossProjectAgents.find((a) => a.id === agentId);
  return cross ? { node: cross, owner: null } : null;
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isOptStr = (v: unknown): v is string | undefined => v === undefined || typeof v === "string";
const PROVENANCE: ReadonlySet<unknown> = new Set(["pre-backend", "backend"]);
const RUN_STATES: ReadonlySet<unknown> = new Set(["in_progress", "completed", "failed", "stopped", "not_found"]);

function agentProblems(v: unknown, at: string): string[] {
  if (!isObject(v)) return [`${at}: not an object`];
  const out: string[] = [];
  if (!isStr(v.id) || !v.id) out.push(`${at}: id must be a non-empty string`);
  if (!isStr(v.viewId) || !v.viewId) out.push(`${at}: viewId must be a non-empty string`);
  if (typeof v.viewOpen !== "boolean") out.push(`${at}: viewOpen must be boolean`);
  if (!isOptStr(v.runId)) out.push(`${at}: runId must be a string when present`);
  const kind = v.kind;
  if (!isStr(kind) || !Object.hasOwn(AGENT_RUN_KIND_OF_TAB, kind)) out.push(`${at}: unknown kind ${JSON.stringify(kind)}`);
  else if (v.runKind !== AGENT_RUN_KIND_OF_TAB[kind as AgentTabKind]) {
    out.push(`${at}: runKind ${JSON.stringify(v.runKind)} disagrees with AGENT_RUN_KIND_OF_TAB[${kind}]`);
  }
  if (v.scope !== "project" && v.scope !== "cross-project") out.push(`${at}: unknown scope ${JSON.stringify(v.scope)}`);
  if (v.scopeProvenance !== "session-global" && v.scopeProvenance !== "registry-member" && v.scopeProvenance !== "backend") {
    out.push(`${at}: unknown scopeProvenance ${JSON.stringify(v.scopeProvenance)}`);
  }
  if (v.projectId !== null && !isStr(v.projectId)) out.push(`${at}: projectId must be a string or null`);
  if (v.scope === "cross-project" && v.projectId !== null) out.push(`${at}: cross-project agent with a non-null projectId`);
  if (v.scope === "project" && v.projectId === null) out.push(`${at}: project-scoped agent with a null projectId`);
  if (v.scope === "project" && v.scopeProvenance === "session-global") {
    out.push(`${at}: project scope cannot come from session-global provenance`);
  }
  if (!isOptStr(v.investigationId)) out.push(`${at}: investigationId must be a string when present`);
  if (!isOptStr(v.documentId)) out.push(`${at}: documentId must be a string when present`);
  if (!isStr(v.title)) out.push(`${at}: title must be a string`);
  if (!PROVENANCE.has(v.provenance)) out.push(`${at}: unknown provenance ${JSON.stringify(v.provenance)}`);
  if (v.status !== undefined) {
    const s = v.status;
    if (!isObject(s) || !RUN_STATES.has(s.state) || (s.since !== null && !isStr(s.since)) ||
      (s.lastSeen !== null && !isStr(s.lastSeen)) || (s.freshness !== "live" && s.freshness !== "stale") || !PROVENANCE.has(s.provenance)) {
      out.push(`${at}: malformed status`);
    }
  }
  // Provenance labels a pre-backend agent may not wear (CONTRACTS.md §2):
  // a run id (never fabricated), a backend-decided scope, a backend status.
  if (v.provenance === "pre-backend") {
    if (v.runId !== undefined) out.push(`${at}: pre-backend agent with a runId`);
    if (v.scopeProvenance === "backend") out.push(`${at}: pre-backend agent with backend scope provenance`);
    if (isObject(v.status) && v.status.provenance === "backend") out.push(`${at}: pre-backend agent with a backend status`);
  }
  return out;
}

function nodeProblems(v: unknown, at: string, seenIds: Set<string>): string[] {
  if (!isObject(v)) return [`${at}: not an object`];
  const out: string[] = [];
  if (!isStr(v.id) || !v.id) out.push(`${at}: id must be a non-empty string`);
  else if (seenIds.has(v.id)) out.push(`${at}: duplicate node id ${v.id}`);
  else seenIds.add(v.id);
  if (v.kind !== "project" && v.kind !== "subproject") out.push(`${at}: unknown kind ${JSON.stringify(v.kind)}`);
  if (!isStr(v.title)) out.push(`${at}: title must be a string`);
  if (v.parentId !== null && !isStr(v.parentId)) out.push(`${at}: parentId must be a string or null`);
  if (v.kind === "subproject" && v.parentId === null) out.push(`${at}: subproject with a null parentId`);
  if (typeof v.archived !== "boolean") out.push(`${at}: archived must be boolean`);
  if (!PROVENANCE.has(v.provenance)) out.push(`${at}: unknown provenance ${JSON.stringify(v.provenance)}`);
  if (v.members !== undefined && !Array.isArray(v.members)) out.push(`${at}: members must be an array when present`);
  if (v.memberCount !== undefined && typeof v.memberCount !== "number") out.push(`${at}: memberCount must be a number when present`);
  const src = v.source;
  if (!isObject(src)) out.push(`${at}: source missing`);
  else if (src.kind === "registry") {
    if (!isObject(src.project) || !isStr(src.project.project_id)) out.push(`${at}: registry source without a project`);
  } else if (src.kind === "investigation") {
    if (v.provenance === "backend") out.push(`${at}: investigation source with backend provenance`);
    if (typeof src.parentMissing !== "boolean") out.push(`${at}: parentMissing must be boolean`);
    if (!isObject(src.run) || !isStr(src.run.agentViewId)) out.push(`${at}: run descriptor missing agentViewId`);
    else {
      if (src.run.state !== undefined && !RUN_STATES.has(src.run.state)) out.push(`${at}: unknown run state`);
      if (!isOptStr(src.run.since)) out.push(`${at}: run.since must be a string when present`);
    }
    if (src.summary !== null && !isObject(src.summary)) out.push(`${at}: summary must be an object or null`);
  } else if (src.kind !== "default") out.push(`${at}: unknown source kind ${JSON.stringify(src.kind)}`);
  if (!Array.isArray(v.children)) out.push(`${at}: children must be an array`);
  else v.children.forEach((c, i) => {
    out.push(...nodeProblems(c, `${at}.children[${i}]`, seenIds));
    if (isObject(c) && c.parentId !== v.id) out.push(`${at}.children[${i}]: parentId ${JSON.stringify(c.parentId)} is not the parent's id`);
  });
  if (!Array.isArray(v.agents)) out.push(`${at}: agents must be an array`);
  else v.agents.forEach((a, i) => {
    out.push(...agentProblems(a, `${at}.agents[${i}]`));
    if (isObject(a) && a.scope === "cross-project") out.push(`${at}.agents[${i}]: cross-project agent ${String(a.id)} filed under a node`);
  });
  return out;
}

export function isAgentNode(v: unknown): v is AgentNode {
  return agentProblems(v, "agent").length === 0;
}

export function isProjectNode(v: unknown): v is ProjectNode {
  return nodeProblems(v, "node", new Set()).length === 0;
}

export function isContextTree(v: unknown): v is ContextTree {
  if (!isObject(v) || !Array.isArray(v.roots) || !Array.isArray(v.crossProjectAgents)) return false;
  if (!PROVENANCE.has(v.provenance)) return false;
  if (v.status !== "unfed" && v.status !== "loading" && v.status !== "ready" && v.status !== "error") return false;
  if (v.error !== null && !isStr(v.error)) return false;
  return checkTree(v as unknown as ContextTree).length === 0;
}

/** Pure invariant checker for tests and SPR-10 status; [] when sound. */
export function checkTree(tree: ContextTree): string[] {
  const out: string[] = [];
  const seenIds = new Set<string>();
  tree.roots.forEach((r, i) => {
    out.push(...nodeProblems(r, `roots[${i}]`, seenIds));
    if (isObject(r) && r.parentId !== null) out.push(`roots[${i}]: a root must have parentId null`);
  });
  tree.crossProjectAgents.forEach((a, i) => {
    out.push(...agentProblems(a, `crossProjectAgents[${i}]`));
    if (isObject(a) && a.scope !== "cross-project") out.push(`crossProjectAgents[${i}]: ${String(a.id)} is not cross-project`);
  });
  if (out.length > 0) return out;

  // Ownership census: a project-scoped agent has exactly one owner whose id
  // is its projectId; a cross-project agent appears exactly once in
  // crossProjectAgents and never under a node.
  const owners = new Map<string, ProjectNode[]>();
  let anyPreBackend = false;
  const walk = (n: ProjectNode) => {
    if (n.provenance === "pre-backend") anyPreBackend = true;
    for (const a of n.agents) {
      if (a.provenance === "pre-backend") anyPreBackend = true;
      owners.set(a.id, [...(owners.get(a.id) ?? []), n]);
    }
    n.children.forEach(walk);
  };
  tree.roots.forEach(walk);
  for (const [id, nodes] of owners) {
    if (nodes.length !== 1) out.push(`agent ${id} owned by ${nodes.length} nodes`);
    for (const n of nodes) {
      const a = n.agents.find((x) => x.id === id)!;
      if (a.projectId !== n.id) out.push(`agent ${id} filed under ${n.id} but projectId is ${JSON.stringify(a.projectId)}`);
    }
  }
  const crossCount = new Map<string, number>();
  for (const a of tree.crossProjectAgents) {
    if (a.provenance === "pre-backend") anyPreBackend = true;
    crossCount.set(a.id, (crossCount.get(a.id) ?? 0) + 1);
    if (owners.has(a.id)) out.push(`cross-project agent ${a.id} also filed under a node`);
  }
  for (const [id, n] of crossCount) if (n !== 1) out.push(`cross-project agent ${id} listed ${n} times`);
  if (anyPreBackend && tree.provenance !== "pre-backend") out.push(`tree provenance must be pre-backend while any node is`);
  return out;
}
