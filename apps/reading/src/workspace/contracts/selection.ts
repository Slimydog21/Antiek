/**
 * contracts/selection.ts — the one selection store (SPR-06 M1/M3).
 * LAZY module: it imports tabTreeStore's values, so entry-chunk code
 * dynamic-imports `./contracts` the way shortcuts.ts imports companionStore.
 *
 * `projectId` is a MIRROR of tabTreeStore.projectId, fed by one
 * `useTabTrees.subscribe`. That subscription covers every way the selected
 * project changes today: `selectProject` (tabTreeStore.ts:514-527), the
 * owner subscription's re-seed `setState({projectId: readTabProject() ??
 * TAB_PROJECT_ID})` (tabTreeStore.ts:745-756) and `setTabTreeAdapter` /
 * `resetTabTrees` (an epoch bump). Each clears sub/agent, which keeps the
 * selection a prefix of a tree path across account switches without an
 * auth.tsx entry; testAccountOwner.ts's `resetTabTrees()` resets it for free.
 *
 * `selectProject` here is THE one production writer of the selected project
 * (writerCensus.test.ts). It never calls through "just to be sure": a
 * tabTreeStore.selectProject discards pendingOps and held closes, so a
 * same-id call is a no-op by contract. tabTreeStore.selectProject stays the
 * only caller of persistence.writeTabProject/clearTabProject.
 *
 * Sub-project and agent selection are session-only: no new storage key
 * before SPR-B names one.
 */
import { create } from "zustand";

import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { findAgent, findProjectPath, type ContextTree } from "./tree";

export interface Selection {
  /** Mirror of tabTreeStore.projectId; TAB_PROJECT_ID when none. backend:
   *  the selected Project.project_id (persisted at
   *  antiek.workspace.tab-project, persistence.ts:441-504). */
  projectId: string;
  /** Deepest selected ProjectNode under projectId (a raw investigation_id pre-backend). */
  subProjectId?: string;
  /** AgentNode.id (run identity, not viewId). */
  agentId?: string;
}

export interface SelectionState {
  /** Frozen; replaced only when a field differs. */
  selection: Selection;
  /** Mirrors tabTreeStore.contextEpoch. */
  epoch: number;
  /** THE one writer. Trims; "" ⇒ false; same id ⇒ false; else
   *  useTabTrees.getState().selectProject(id); true. */
  selectProject(projectId: string): boolean;
  /** Writes iff isSelectionPathOf(candidate, tree); null clears (and clears agentId). */
  selectSubProject(id: string | null, tree: ContextTree): boolean;
  /** Writes iff the agent is filed on the current path or is cross-project; null clears. */
  selectAgent(id: string | null, tree: ContextTree): boolean;
  /** Called by treeStore on every publish: drops a sub/agent no longer on the path. Keeps projectId. */
  reconcile(tree: ContextTree): void;
}

/** [projectId, subProjectId?, agentId?] */
export function selectionPath(s: Selection): string[] {
  const out = [s.projectId];
  if (s.subProjectId !== undefined) out.push(s.subProjectId);
  if (s.agentId !== undefined) out.push(s.agentId);
  return out;
}

/** True iff the selection is a prefix of a tree path: the deepest selected
 *  node's root is projectId, and the agent (if any) is owned by a node on
 *  that path or is cross-project. */
export function isSelectionPathOf(s: Selection, tree: ContextTree): boolean {
  const path = findProjectPath(tree, s.subProjectId ?? s.projectId);
  if (!path || path[0].id !== s.projectId) return false;
  if (s.agentId === undefined) return true;
  const found = findAgent(tree, s.agentId);
  if (!found) return false;
  if (found.node.scope === "cross-project") return true;
  return found.owner !== null && path.some((n) => n.id === found.owner!.id);
}

function same(a: Selection, b: Selection): boolean {
  return a.projectId === b.projectId && a.subProjectId === b.subProjectId && a.agentId === b.agentId;
}

function freeze(s: Selection): Selection {
  return Object.freeze({
    projectId: s.projectId,
    ...(s.subProjectId !== undefined ? { subProjectId: s.subProjectId } : {}),
    ...(s.agentId !== undefined ? { agentId: s.agentId } : {}),
  });
}

export const useSelection = create<SelectionState>()((set, get) => ({
  selection: freeze({ projectId: useTabTrees.getState().projectId || TAB_PROJECT_ID }),
  epoch: useTabTrees.getState().contextEpoch,

  selectProject: (projectId) => {
    const id = projectId.trim();
    if (!id) return false;
    if (useTabTrees.getState().projectId === id) return false;
    useTabTrees.getState().selectProject(id);
    return true;
  },

  selectSubProject: (id, tree) => {
    const cur = get().selection;
    if (id === null) {
      if (cur.subProjectId === undefined && cur.agentId === undefined) return false;
      set({ selection: freeze({ projectId: cur.projectId }) });
      return true;
    }
    const base: Selection = { projectId: cur.projectId, subProjectId: id };
    if (!isSelectionPathOf(base, tree)) return false;
    const withAgent: Selection = cur.agentId !== undefined ? { ...base, agentId: cur.agentId } : base;
    const next = isSelectionPathOf(withAgent, tree) ? withAgent : base;
    if (same(next, cur)) return false;
    set({ selection: freeze(next) });
    return true;
  },

  selectAgent: (id, tree) => {
    const cur = get().selection;
    if (id === null) {
      if (cur.agentId === undefined) return false;
      const { agentId: _drop, ...rest } = cur;
      set({ selection: freeze(rest) });
      return true;
    }
    const next: Selection = { ...cur, agentId: id };
    if (!isSelectionPathOf(next, tree)) return false;
    if (same(next, cur)) return false;
    set({ selection: freeze(next) });
    return true;
  },

  reconcile: (tree) => {
    const cur = get().selection;
    if (cur.subProjectId === undefined && cur.agentId === undefined) return;
    if (isSelectionPathOf(cur, tree)) return;
    // Keep the longest prefix that still holds; projectId always stays.
    const noAgent: Selection = { projectId: cur.projectId, ...(cur.subProjectId !== undefined ? { subProjectId: cur.subProjectId } : {}) };
    const next = cur.agentId !== undefined && isSelectionPathOf(noAgent, tree) ? noAgent : { projectId: cur.projectId };
    if (!same(next, cur)) set({ selection: freeze(next) });
  },
}));

// The mirror: one subscription for every way the selected project changes.
useTabTrees.subscribe((s, p) => {
  if (s.projectId !== p.projectId || s.contextEpoch !== p.contextEpoch) {
    useSelection.setState({ selection: freeze({ projectId: s.projectId || TAB_PROJECT_ID }), epoch: s.contextEpoch });
  }
});

/** The row's place in the tree. Pre-backend the id spaces overlap: a
 *  research agent's id IS its investigation id, which is also a sub-project
 *  node's id, so a raw-id check would light a sibling sub-project row off
 *  the selected path (the rendered selection would no longer be a prefix
 *  of one tree path). The role keeps the three fields apart. */
export type SelectionRole = "project" | "subproject" | "agent";

/** The one row selector SPR-04 consumes: `selection[role] === id`. A
 *  boolean selector, so a row re-renders only when its own answer flips. */
export function useIsSelected(id: string, role: SelectionRole): boolean {
  return useSelection((s) => {
    if (role === "project") return s.selection.projectId === id;
    if (role === "subproject") return s.selection.subProjectId === id;
    if (role === "agent") return s.selection.agentId === id;
    return false; // an untyped caller with no role lights nothing, never a sibling row
  });
}
