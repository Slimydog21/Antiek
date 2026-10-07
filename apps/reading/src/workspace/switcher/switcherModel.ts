/**
 * switcherModel.ts — SPR-04 M1: the gears as a PURE function of the SPR-06
 * tree and selection (specs/antiek-keyboard-panes-agents-20261007/
 * sprint-04-geared-switcher.html). No store, no React, no DOM.
 *
 *   gear 1  the forest's roots (projects); selected = selection.projectId
 *   gear 2  the selected root's children, pinned at depth 1; selected =
 *           the depth-1 node on the path (never a deeper one)
 *   gear 3  the deepest selected node's agents, then (with a sub-project
 *           selected) its children as drill targets, then the cross-project
 *           agents after a divider; selected = selection.agentId
 *
 * Status before stale: a loading/error/unfed tree reports itself, and only
 * a ready tree can call a selection stale. Strips still derive from the
 * retained roots while loading, so an empty strip then says "loading" and
 * never "not in the list" (F2 in the handoff).
 *
 * Provenance never leaks (rigor #1): every label comes from `displayKind`,
 * and "Sub-projects" is the gear-2 heading only when every listed node is
 * backend-asserted. Copy for the empty reasons lives in GearSwitch.tsx, so
 * this model never spells a sentence that asserts absence.
 *
 * Entry-safe by construction? No: it is consumed only by the lazy
 * GearSwitch chunk. Value imports are confined to `../contracts/tree`
 * (switcherChunk.test.ts), so the model stays a leaf of the contract.
 */
import type { Selection, SelectionRole } from "../contracts/selection";
import {
  displayKind,
  findAgent,
  findProjectPath,
  type AgentNode,
  type AgentScope,
  type ContextTree,
  type ProjectNode,
  type ProjectNodeSource,
  type Provenance,
  type TreeStatus,
} from "../contracts/tree";

export type Gear = 1 | 2 | 3;

/** Why a strip is empty. The surface translates; the model never spells copy. */
export type EmptyReason =
  | "unfed" | "loading" | "error" | "stale-project"
  | "no-children" | "not-linked" | "none-listed" | "no-agents";

export type AgentTabKind = AgentNode["kind"];

export interface GearTab {
  role: SelectionRole;
  /** Raw node or agent id (never prefixed). */
  id: string;
  /** React key + DOM id; survives the pre-backend id overlap (a research
   *  agent's id IS its investigation id, selection.ts:150-154). */
  key: `${SelectionRole}:${string}`;
  label: string;
  kindLabel: string;
  selected: boolean;
  /** Something lies behind Enter (children or agents). Informational. */
  deeper: boolean;
  parentId: string | null;
  agent?: { viewId: string; viewOpen: boolean; kind: AgentTabKind; investigationId?: string; scope: AgentScope };
  node?: { provenance: Provenance; sourceKind: ProjectNodeSource["kind"]; route: string | null };
}

export interface GearStrip {
  gear: Gear;
  heading: string;
  tabs: readonly GearTab[];
  empty: EmptyReason | null;
  /** Index of the first cross-project agent (the "Across projects" divider), or null. */
  crossProjectFrom: number | null;
}

export interface SwitcherModel {
  status: TreeStatus | "stale";
  error: string | null;
  /** root … deepest node, then the selected agent: what the closed chip reads. */
  path: readonly GearTab[];
  strips: readonly [GearStrip, GearStrip, GearStrip];
}

/** "Sub-projects" only when every listed node is backend-asserted. */
export function gearHeading(gear: Gear, nodes: readonly ProjectNode[]): string {
  if (gear === 1) return "Projects";
  if (gear === 3) return "Agents";
  return nodes.length > 0 && nodes.every((n) => n.provenance === "backend") ? "Sub-projects" : "Investigations";
}

function routeOf(n: ProjectNode): string | null {
  return n.source.kind === "investigation" ? `/inv/${n.id}` : null;
}

function nodeTab(n: ProjectNode, role: SelectionRole, selected: boolean): GearTab {
  return {
    role,
    id: n.id,
    key: `${role}:${n.id}`,
    label: n.title,
    kindLabel: displayKind(n),
    selected,
    deeper: n.children.length > 0 || n.agents.length > 0,
    parentId: n.parentId,
    node: { provenance: n.provenance, sourceKind: n.source.kind, route: routeOf(n) },
  };
}

function agentTab(a: AgentNode, selected: boolean): GearTab {
  return {
    role: "agent",
    id: a.id,
    key: `agent:${a.id}`,
    label: a.title,
    kindLabel: "Agent",
    selected,
    deeper: false,
    parentId: a.projectId,
    agent: {
      viewId: a.viewId,
      viewOpen: a.viewOpen,
      kind: a.kind,
      ...(a.investigationId !== undefined ? { investigationId: a.investigationId } : {}),
      scope: a.scope,
    },
  };
}

/** Why gear 2 is empty under `root`, by provenance (grafts 7+8). */
function gear2Empty(root: ProjectNode): EmptyReason {
  if (root.provenance === "backend") return "no-children";
  if (root.source.kind === "registry") return "not-linked";
  return "none-listed";
}

export function deriveSwitcher(tree: ContextTree, selection: Selection): SwitcherModel {
  const rawPath = findProjectPath(tree, selection.subProjectId ?? selection.projectId);
  const stale = rawPath === null || rawPath[0].id !== selection.projectId;
  const status: SwitcherModel["status"] = tree.status !== "ready" ? tree.status : stale ? "stale" : "ready";
  // A non-ready status names an empty strip; a ready-but-stale one says so.
  const emptyFor = (reason: EmptyReason): EmptyReason =>
    tree.status !== "ready" ? (tree.status as EmptyReason) : stale ? "stale-project" : reason;

  const nodePath: readonly ProjectNode[] = stale ? [] : rawPath;
  const root = nodePath[0] ?? null;
  const deepest = nodePath.at(-1) ?? null;

  // The selected agent, admitted only on this path (or cross-project).
  const hit = !stale && selection.agentId !== undefined ? findAgent(tree, selection.agentId) : null;
  const agentOnPath = hit !== null && (hit.node.scope === "cross-project" || (hit.owner !== null && nodePath.some((n) => n.id === hit.owner!.id)));

  // Gear 1: the roots.
  const g1Tabs = tree.roots.map((r) => nodeTab(r, "project", !stale && r.id === selection.projectId));

  // Gear 2: the root's children, pinned at depth 1.
  const g2Nodes = root ? root.children : NO_NODES;
  const depth1 = nodePath[1]?.id;
  const g2Tabs = g2Nodes.map((n) => nodeTab(n, "subproject", n.id === depth1));

  // Gear 3: agents, drill targets (only with a sub-project selected), cross-project agents.
  const ownAgents = deepest ? deepest.agents : NO_AGENTS;
  const drill = deepest && selection.subProjectId !== undefined ? deepest.children : NO_NODES;
  const cross = stale ? NO_AGENTS : tree.crossProjectAgents;
  const g3Tabs: GearTab[] = [
    ...ownAgents.map((a) => agentTab(a, agentOnPath && a.id === selection.agentId)),
    ...drill.map((n) => nodeTab(n, "subproject", false)),
    ...cross.map((a) => agentTab(a, agentOnPath && a.id === selection.agentId)),
  ];
  const crossProjectFrom = cross.length ? ownAgents.length + drill.length : null;

  const strip = (gear: Gear, heading: string, tabs: readonly GearTab[], reason: EmptyReason, from: number | null): GearStrip => ({
    gear,
    heading,
    tabs,
    empty: tabs.length ? null : emptyFor(reason),
    crossProjectFrom: tabs.length ? from : null,
  });

  const path: GearTab[] = [
    ...nodePath.map((n, i) => nodeTab(n, i === 0 ? "project" : "subproject", true)),
    ...(agentOnPath ? [agentTab(hit.node, true)] : []),
  ];

  return {
    status,
    error: tree.error,
    path,
    strips: [
      strip(1, gearHeading(1, tree.roots), g1Tabs, "none-listed", null),
      strip(2, gearHeading(2, g2Nodes), g2Tabs, root ? gear2Empty(root) : "stale-project", null),
      strip(3, gearHeading(3, []), g3Tabs, "no-agents", crossProjectFrom),
    ],
  };
}

const NO_NODES: readonly ProjectNode[] = Object.freeze([]);
const NO_AGENTS: readonly AgentNode[] = Object.freeze([]);
