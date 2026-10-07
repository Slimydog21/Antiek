/**
 * treeStore.test.ts — SPR-06: the provenance-neutral tree store reuses node
 * identity by fingerprint, publishes by reference when nothing changed, and
 * reconciles the selection on every publish.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, renderHook } from "@testing-library/react";

import { clearTabProject } from "../persistence";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { composePreBackendTree } from "./adapters/preBackend";
import { SUMMARIES, fixtureInputs, tabs } from "./fixtures.test.helpers";
import { useSelection } from "./selection";
import type { ContextTree, ProjectNode } from "./tree";
import {
  markTreeError,
  markTreeUnfed,
  publishTree,
  useContextTree,
  useContextTreeStore,
  useSelectedProjectNode,
} from "./treeStore";

const byId = (tree: ContextTree): Map<string, ProjectNode> => {
  const m = new Map<string, ProjectNode>();
  const walk = (n: ProjectNode) => { m.set(n.id, n); n.children.forEach(walk); };
  tree.roots.forEach(walk);
  return m;
};

function resetAll() {
  useTabTrees.getState().resetTabTrees();
  useTabTrees.getState().selectProject(TAB_PROJECT_ID);
  clearTabProject();
  markTreeUnfed();
}

beforeEach(resetAll);
afterEach(() => { cleanup(); resetAll(); });

describe("R1 identity reuse", () => {
  it("the same content from fresh arrays publishes the previous tree by reference", () => {
    publishTree(composePreBackendTree(fixtureInputs()), "t1");
    const first = useContextTreeStore.getState().tree;
    let renders = 0;
    function Probe() { renders += 1; useContextTree((t) => t.roots); return null; }
    render(<Probe />);
    act(() => {
      publishTree(composePreBackendTree(fixtureInputs({ investigations: [...SUMMARIES], companionTabs: tabs() })), "t2");
      publishTree(composePreBackendTree(fixtureInputs({ investigations: SUMMARIES.map((s) => ({ ...s })) })), "t3");
    });
    expect(Object.is(useContextTreeStore.getState().tree, first)).toBe(true);
    expect(useContextTreeStore.getState().composedAt).toBe("t3");
    expect(renders).toBe(1);
  });
});

describe("R2 minimal replacement", () => {
  it("one status change replaces only that node and its ancestors", () => {
    publishTree(composePreBackendTree(fixtureInputs()), "t1");
    const before = byId(useContextTreeStore.getState().tree);
    const changed = SUMMARIES.map((s) => (s.investigation_id === "inv-child" ? { ...s, status: "completed" as const } : s));
    publishTree(composePreBackendTree(fixtureInputs({ investigations: changed })), "t2");
    const after = byId(useContextTreeStore.getState().tree);
    expect(after.get("inv-child")).not.toBe(before.get("inv-child"));
    expect(after.get("inv-root")).not.toBe(before.get("inv-root"));
    expect(after.get("default")).not.toBe(before.get("default"));
    for (const id of after.keys()) {
      if (["inv-child", "inv-root", "default"].includes(id)) continue;
      expect(after.get(id), id).toBe(before.get(id));
    }
    // The agent that watches inv-child changed (its status), nothing else did.
    const agentsBefore = before.get("p1")!.agents;
    expect(after.get("p1")!.agents).toBe(agentsBefore);
  });
  it("a companion activeTabId/seq change produces no new tree", () => {
    publishTree(composePreBackendTree(fixtureInputs()), "t1");
    const first = useContextTreeStore.getState().tree;
    const reseq = tabs().map((t, i) => ({ ...t, seq: 100 + i }));
    publishTree(composePreBackendTree(fixtureInputs({ companionTabs: reseq })), "t2");
    expect(Object.is(useContextTreeStore.getState().tree, first)).toBe(true);
  });
});

describe("R3 reconcile", () => {
  it("drops a selected sub-project that vanished, keeps projectId", () => {
    const tree = composePreBackendTree(fixtureInputs());
    publishTree(tree, "t1");
    expect(useSelection.getState().selectSubProject("inv-orphan", tree)).toBe(true);
    const without = SUMMARIES.filter((s) => s.investigation_id !== "inv-orphan");
    publishTree(composePreBackendTree(fixtureInputs({ investigations: without })), "t2");
    expect(useSelection.getState().selection).toEqual({ projectId: TAB_PROJECT_ID });
  });
});

describe("R4 status", () => {
  it("unfed, then ready, then error keeps roots", () => {
    const s = useContextTreeStore.getState().tree;
    expect(s.status).toBe("unfed");
    expect(s.roots).toHaveLength(0);
    publishTree(composePreBackendTree(fixtureInputs()), "t1");
    expect(useContextTreeStore.getState().tree.status).toBe("ready");
    const roots = useContextTreeStore.getState().tree.roots;
    markTreeError("boom");
    const t = useContextTreeStore.getState().tree;
    expect(t.status).toBe("error");
    expect(t.error).toBe("boom");
    expect(t.roots).toBe(roots);
  });
});

describe("R5 useSelectedProjectNode", () => {
  it("is null for a persisted id absent from the registry", () => {
    publishTree(composePreBackendTree(fixtureInputs()), "t1");
    useSelection.getState().selectProject("ghost-project");
    const { result } = renderHook(() => useSelectedProjectNode());
    expect(result.current).toBeNull();
    act(() => { useSelection.getState().selectProject("p1"); });
    expect(result.current?.id).toBe("p1");
  });
});
