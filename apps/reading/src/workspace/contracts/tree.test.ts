/**
 * tree.test.ts — SPR-06 M1 invariants for the typed context tree.
 *   T1 agent-in-one-project   T2 view-id reproduction   T3 guard rejections
 *   T4 displayKind lens        T5 run-kind table covers every tab kind
 */
import { afterEach, describe, expect, it } from "vitest";

import { AGENT_TAB_KINDS } from "../companionRegistry";
import { useCompanion } from "../companionStore";
import { composePreBackendTree } from "./adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers } from "./fixtures.test.helpers";
import {
  AGENT_RUN_KIND_OF_TAB,
  agentViewId,
  checkTree,
  displayKind,
  findAgent,
  isAgentNode,
  isProjectNode,
  type AgentNode,
  type ContextTree,
  type ProjectNode,
} from "./tree";

function allNodes(tree: ContextTree): ProjectNode[] {
  const out: ProjectNode[] = [];
  const walk = (n: ProjectNode) => { out.push(n); n.children.forEach(walk); };
  tree.roots.forEach(walk);
  return out;
}

function mapNodes(tree: ContextTree, f: (n: ProjectNode) => ProjectNode): ContextTree {
  const walk = (n: ProjectNode): ProjectNode => f({ ...n, children: n.children.map(walk) });
  return { ...tree, roots: tree.roots.map(walk) };
}

describe("T1 agent-in-one-project", () => {
  it("the adapter fixture is sound", () => {
    expect(checkTree(composePreBackendTree(fixtureInputs()))).toEqual([]);
    expect(checkTree(composePreBackendTree(fixtureInputsWithMembers()))).toEqual([]);
  });

  it("a project-scoped agent owned by two nodes is exactly one violation", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    const found = findAgent(tree, "inv-member");
    expect(found?.node.scope).toBe("project");
    const agent = found!.node;
    const dup = mapNodes(tree, (n) => (n.id === "p2" ? { ...n, agents: [agent] } : n));
    const owned = checkTree(dup).filter((v) => /owned by 2 nodes/.test(v));
    expect(owned).toEqual([`agent inv-member owned by 2 nodes`]);
  });

  it("a cross-project agent inside any agents list is a violation", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const dialogue = tree.crossProjectAgents.find((a) => a.kind === "dialogue")!;
    const bad = mapNodes(tree, (n) => (n.id === "default" ? { ...n, agents: [...n.agents, dialogue] } : n));
    expect(checkTree(bad).some((v) => v.includes("cross-project") && v.includes(dialogue.id))).toBe(true);
  });
});

describe("T2 agentViewId reproduces companionStore's tab id", () => {
  afterEach(() => useCompanion.getState().reset());
  it("research-thread and dialogue", () => {
    expect(agentViewId("research-thread", "inv-1")).toBe(
      useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "inv-1" }),
    );
    expect(agentViewId("dialogue")).toBe(useCompanion.getState().openAgentTab({ kind: "dialogue" }));
  });
});

describe("T3 guards", () => {
  const agent: AgentNode = {
    id: "inv-1", viewId: "agent:thread:inv-1", viewOpen: true, kind: "research-thread", runKind: "research",
    scope: "cross-project", scopeProvenance: "session-global", projectId: null, investigationId: "inv-1",
    title: "t", provenance: "pre-backend",
  };
  const sub: ProjectNode = {
    id: "inv-1", kind: "subproject", title: "t", parentId: "default", children: [], agents: [], archived: false,
    provenance: "pre-backend",
    source: { kind: "investigation", summary: null, parentMissing: false, run: { agentViewId: "agent:thread:inv-1" } },
  };
  it("accepts the sound shapes", () => {
    expect(isAgentNode(agent)).toBe(true);
    expect(isProjectNode(sub)).toBe(true);
  });
  it("rejects investigation source with backend provenance", () => {
    expect(isProjectNode({ ...sub, provenance: "backend" })).toBe(false);
  });
  it("rejects a subproject with a null parent", () => {
    expect(isProjectNode({ ...sub, parentId: null })).toBe(false);
  });
  it("rejects cross-project with a non-null projectId", () => {
    expect(isAgentNode({ ...agent, projectId: "p1" })).toBe(false);
  });
  it("rejects project scope with session-global provenance", () => {
    expect(isAgentNode({ ...agent, scope: "project", projectId: "p1" })).toBe(false);
  });
  it("rejects project scope with a null projectId", () => {
    expect(isAgentNode({ ...agent, scope: "project", scopeProvenance: "registry-member", projectId: null })).toBe(false);
  });
  it("rejects runKind that disagrees with the table", () => {
    expect(isAgentNode({ ...agent, runKind: "dialogue" })).toBe(false);
  });
  it("rejects a pre-backend agent with a runId (never fabricated)", () => {
    expect(isAgentNode({ ...agent, runId: "run-1" })).toBe(false);
    expect(isAgentNode({ ...agent, runId: "run-1", provenance: "backend" })).toBe(true);
  });
  it("rejects a pre-backend agent claiming backend scope provenance", () => {
    expect(isAgentNode({ ...agent, scope: "project", projectId: "p1", scopeProvenance: "backend" })).toBe(false);
    expect(isAgentNode({ ...agent, scope: "project", projectId: "p1", scopeProvenance: "backend", provenance: "backend" })).toBe(true);
  });
  it("rejects a pre-backend agent carrying a backend status", () => {
    const status = { state: "completed" as const, since: null, lastSeen: null, freshness: "live" as const, provenance: "backend" as const };
    expect(isAgentNode({ ...agent, status })).toBe(false);
    expect(isAgentNode({ ...agent, status: { ...status, provenance: "pre-backend" } })).toBe(true);
    expect(isAgentNode({ ...agent, status, provenance: "backend" })).toBe(true);
  });
});

describe("T6 provenance labels are checked, not commented", () => {
  it("checkTree names each forged label on a pre-backend agent", () => {
    const tree = composePreBackendTree(fixtureInputs());
    const a = tree.crossProjectAgents.find((x) => x.kind === "research-thread" && x.status)!;
    const forged: AgentNode = { ...a, runId: "fabricated-run", scopeProvenance: "backend", status: { ...a.status!, provenance: "backend" } };
    const bad: ContextTree = { ...tree, crossProjectAgents: tree.crossProjectAgents.map((x) => (x === a ? forged : x)) };
    const at = `crossProjectAgents[${tree.crossProjectAgents.indexOf(a)}]`;
    expect(checkTree(bad)).toEqual([
      `${at}: pre-backend agent with a runId`,
      `${at}: pre-backend agent with backend scope provenance`,
      `${at}: pre-backend agent with a backend status`,
    ]);
  });
});

describe("T4 displayKind", () => {
  it("never says Sub-project for a pre-backend node", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    for (const n of allNodes(tree)) {
      expect(n.provenance).toBe("pre-backend");
      expect(displayKind(n)).not.toBe("Sub-project");
    }
    expect(displayKind(tree.roots[0])).toBe("Default project");
    expect(displayKind(tree.roots.find((n) => n.id === "p1")!)).toBe("Project");
    expect(displayKind(tree.roots[0].children[0])).toBe("Investigation");
  });
  it("says Sub-project only for a backend subproject", () => {
    const backend: ProjectNode = {
      id: "s", kind: "subproject", title: "s", parentId: "p", children: [], agents: [], archived: false,
      provenance: "backend", source: { kind: "registry", project: { project_id: "s", title: "s", kind: "project", order: 1, pinned: false, archived_at: null, primary_document_id: null, created_at: "", updated_at: null, member_count: 0 } },
    };
    expect(displayKind(backend)).toBe("Sub-project");
  });
});

describe("T5 AGENT_RUN_KIND_OF_TAB", () => {
  it("covers every registered tab kind", () => {
    expect(Object.keys(AGENT_RUN_KIND_OF_TAB).sort()).toEqual(Object.keys(AGENT_TAB_KINDS).sort());
    expect(AGENT_RUN_KIND_OF_TAB["research-thread"]).toBe("research");
  });
});
