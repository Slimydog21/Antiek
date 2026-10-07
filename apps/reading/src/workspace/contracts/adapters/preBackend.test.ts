/**
 * preBackend.test.ts — SPR-06 M2: the pre-backend adapter composes registry
 * projects + the investigation forest + companion tabs into a ContextTree
 * on fixtures (a project with members but no investigations; an orphan; a
 * cycle; a self-parent; a dialogue tab; an unknown research tab; membership).
 */
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";

import { useInvestigationTree } from "../../../hooks/useInvestigationTree";
import { unitAccountKey } from "../../../testAccountOwner";
import {
  MEMBERS_P1,
  SUMMARIES,
  SUMMARIES_ACYCLIC,
  fixtureInputs,
  fixtureInputsWithMembers,
  tab,
} from "../fixtures.test.helpers";
import { checkTree, findAgent, findProjectPath, type AgentNode, type ContextTree, type ProjectNode } from "../tree";
import { composePreBackendTree, readLocalParents } from "./preBackend";

function allNodes(tree: ContextTree): ProjectNode[] {
  const out: ProjectNode[] = [];
  const walk = (n: ProjectNode) => { out.push(n); n.children.forEach(walk); };
  tree.roots.forEach(walk);
  return out;
}
function allFiledAgents(tree: ContextTree): AgentNode[] {
  return allNodes(tree).flatMap((n) => [...n.agents]);
}
const node = (tree: ContextTree, id: string) => allNodes(tree).find((n) => n.id === id);

describe("composePreBackendTree", () => {
  it("(a) a registry project with members and no investigations has empty children and agents", () => {
    const tree = composePreBackendTree(fixtureInputs({
      investigations: [],
      companionTabs: [],
      membersByProject: new Map([["p1", MEMBERS_P1.filter((m) => m.member_kind !== "investigation")]]),
    }));
    const p1 = node(tree, "p1")!;
    expect(p1.kind).toBe("project");
    expect(p1.children).toEqual([]);
    expect(p1.agents).toEqual([]);
    expect(p1.members).toHaveLength(1);
    expect(p1.memberCount).toBe(3);
    expect(p1.archived).toBe(false);
    const p2 = node(tree, "p2")!;
    expect(Object.hasOwn(p2, "members")).toBe(false);
    expect(tree.status).toBe("ready");
    expect(tree.roots.map((r) => r.id)).toEqual(["default", "p1", "p2"]);
  });

  it("(b) a parent outside the list is a root under default with parentMissing", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const orphan = node(tree, "inv-orphan")!;
    expect(orphan.parentId).toBe("default");
    expect(orphan.source.kind === "investigation" && orphan.source.parentMissing).toBe(true);
    expect(findProjectPath(tree, "inv-orphan")!.map((n) => n.id)).toEqual(["default", "inv-orphan"]);
  });

  it("(c) a cycle and a self-parent are promoted to roots; no node is dropped", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const dflt = tree.roots[0];
    const rootIds = dflt.children.map((c) => c.id);
    expect(rootIds).toContain("inv-cycle-a");
    expect(rootIds).toContain("inv-cycle-b");
    expect(rootIds).toContain("inv-self");
    const subprojects = allNodes(tree).filter((n) => n.kind === "subproject");
    expect(subprojects).toHaveLength(SUMMARIES.length);
    expect(new Set(subprojects.map((n) => n.id)).size).toBe(SUMMARIES.length);
    for (const id of ["inv-cycle-a", "inv-cycle-b", "inv-self"]) {
      const n = node(tree, id)!;
      expect(n.parentId).toBe("default");
      expect(n.source.kind === "investigation" && n.source.parentMissing).toBe(false);
    }
  });

  it("(d) provenance, source kind and run descriptors on every node", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    expect(tree.provenance).toBe("pre-backend");
    for (const n of allNodes(tree)) {
      expect(n.provenance).toBe("pre-backend");
      if (n.kind !== "subproject") continue;
      expect(n.source.kind).toBe("investigation");
      if (n.source.kind !== "investigation") continue;
      expect(n.source.run.agentViewId).toBe(`agent:thread:${n.id}`);
      if (n.source.summary) {
        expect(n.source.run.state).toBe(n.source.summary.status);
      } else {
        expect(Object.hasOwn(n.source.run, "state")).toBe(false);
      }
      expect(n.archived).toBe(false);
    }
    for (const a of [...tree.crossProjectAgents, ...allFiledAgents(tree)]) expect(a.provenance).toBe("pre-backend");
    const child = node(tree, "inv-child")!;
    expect(child.source.kind === "investigation" && child.source.run).toEqual({
      agentViewId: "agent:thread:inv-child", state: "in_progress", since: "2026-09-21T10:00:00Z",
    });
    const root = node(tree, "inv-root")!;
    expect(root.source.kind === "investigation" && root.source.run.since).toBe("2026-09-20T12:00:00Z");
    expect(root.title).toBe("Question inv-root");
  });

  it("(e) a dialogue tab is exactly one cross-project agent and never filed", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const dialogues = tree.crossProjectAgents.filter((a) => a.kind === "dialogue");
    expect(dialogues).toHaveLength(1);
    expect(dialogues[0]).toMatchObject({
      id: "agent:dialogue", viewId: "agent:dialogue", viewOpen: true, runKind: "dialogue",
      scope: "cross-project", scopeProvenance: "session-global", projectId: null,
    });
    expect(Object.hasOwn(dialogues[0], "runId")).toBe(false);
    expect(Object.hasOwn(dialogues[0], "investigationId")).toBe(false);
    expect(allFiledAgents(tree).some((a) => a.kind === "dialogue")).toBe(false);
  });

  it("(f) a research tab whose investigation is outside the list is cross-project with no status", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const unknown = tree.crossProjectAgents.find((a) => a.investigationId === "inv-unknown")!;
    expect(unknown).toMatchObject({ id: "inv-unknown", viewId: "agent:thread:inv-unknown", scope: "cross-project", scopeProvenance: "session-global", projectId: null });
    expect(unknown.status).toBeUndefined();
    // A known but unlinked research tab is also cross-project, but carries a status.
    const child = tree.crossProjectAgents.find((a) => a.investigationId === "inv-child")!;
    expect(child.scope).toBe("cross-project");
    expect(child.status).toEqual({ state: "in_progress", since: "2026-09-21T10:00:00Z", lastSeen: null, freshness: "live", provenance: "pre-backend" });
    expect(child.documentId).toBe("doc-1");
    expect(findAgent(tree, "inv-child")).toEqual({ node: child, owner: null });
  });

  it("(g) sibling order equals useInvestigationTree's order", () => {
    const { result } = renderHook(() => useInvestigationTree([...SUMMARIES_ACYCLIC]));
    const hookRoots = result.current.map((n) => n.investigationId);
    const hookRootChildren = result.current.find((n) => n.investigationId === "inv-root")!.children.map((c) => c.investigationId);
    const tree = composePreBackendTree(fixtureInputs({ investigations: SUMMARIES_ACYCLIC }));
    expect(tree.roots[0].children.map((c) => c.id)).toEqual(hookRoots);
    expect(node(tree, "inv-root")!.children.map((c) => c.id)).toEqual(hookRootChildren);
  });

  it("(h) membership files an investigation root and its tab under the project", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    const p1 = node(tree, "p1")!;
    expect(p1.children.map((c) => c.id)).toEqual(["inv-member"]);
    expect(node(tree, "inv-member")!.parentId).toBe("p1");
    const found = findAgent(tree, "inv-member")!;
    expect(found.owner?.id).toBe("inv-member");
    expect(found.node).toMatchObject({ scope: "project", scopeProvenance: "registry-member", projectId: "inv-member" });
    expect(tree.crossProjectAgents.some((a) => a.id === "inv-member")).toBe(false);
    expect(tree.roots[0].children.some((c) => c.id === "inv-member")).toBe(false);
    const bare = composePreBackendTree(fixtureInputs());
    expect(node(bare, "inv-member")!.parentId).toBe("default");
    expect(findAgent(bare, "inv-member")!.owner).toBeNull();
    expect(findAgent(bare, "inv-member")!.node.scope).toBe("cross-project");
  });

  it("(h2) a member investigation outside the list files its tab on the project itself", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers({
      investigations: SUMMARIES.filter((s) => s.investigation_id !== "inv-member"),
    }));
    const found = findAgent(tree, "inv-member")!;
    expect(found.owner?.id).toBe("p1");
    expect(found.node).toMatchObject({ scope: "project", scopeProvenance: "registry-member", projectId: "p1" });
    expect(found.node.status).toBeUndefined();
  });

  it("(i) readLocalParents filters non-string values and is re-read on each call", () => {
    const key = unitAccountKey("antiek:investigation_tree");
    window.localStorage.setItem(key, JSON.stringify({ "inv-orphan": "inv-root", bad: 3, worse: null }));
    expect(readLocalParents()).toEqual({ "inv-orphan": "inv-root" });
    const first = composePreBackendTree(fixtureInputs({ localParents: readLocalParents() }));
    expect(node(first, "inv-orphan")!.parentId).toBe("inv-root");
    window.localStorage.setItem(key, JSON.stringify({ "inv-orphan": "inv-member" }));
    expect(readLocalParents()).toEqual({ "inv-orphan": "inv-member" });
    const second = composePreBackendTree(fixtureInputs({ localParents: readLocalParents() }));
    expect(node(second, "inv-orphan")!.parentId).toBe("inv-member");
    window.localStorage.removeItem(key);
    expect(readLocalParents()).toEqual({});
    // Substrate truth wins over the local map.
    const third = composePreBackendTree(fixtureInputs({ localParents: { "inv-child": "inv-member" } }));
    expect(node(third, "inv-child")!.parentId).toBe("inv-root");
  });

  it("(j) the composed trees are sound", () => {
    expect(checkTree(composePreBackendTree(fixtureInputs()))).toEqual([]);
    expect(checkTree(composePreBackendTree(fixtureInputsWithMembers()))).toEqual([]);
    expect(checkTree(composePreBackendTree(fixtureInputs({ companionTabs: [tab("dialogue"), tab("research-thread", { investigationId: "inv-root" })] })))).toEqual([]);
  });
});
