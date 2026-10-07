/**
 * gearActions.test.tsx — SPR-04 M4: selecting at each gear changes exactly
 * the expected store and no other, on the REAL stores (the in-memory tab
 * tree adapter, useSelection, the context tree store via publishTree,
 * useCompanion, useWorkspace). Rigor #4: selectProject RESETS the trees
 * (tabTreeStore.ts:514-527), so a spawn issued across a switch must land
 * under the new project, not die silently.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers, project } from "../contracts/fixtures.test.helpers";
import { useSelection } from "../contracts/selection";
import type { AgentNode, ContextTree, ProjectNode } from "../contracts/tree";
import { publishTree, useContextTreeStore } from "../contracts/treeStore";
import { useCompanion } from "../companionStore";
import { clearTabProject } from "../persistence";
import { SHORTCUT_EVENTS } from "../shortcuts";
import { createInMemoryTabTreeAdapter } from "../tabTree";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { useWorkspace } from "../WorkspaceStore";
import { runGearEffect } from "./gearActions";
import type { GearEffect } from "./switcherKeys";

const AT = "2026-10-07T22:40:00Z";
const tabs = () => useTabTrees.getState();
const sel = () => useSelection.getState().selection;

function snapshot() {
  const t = tabs();
  return JSON.stringify({
    trees: t.trees, projectId: t.projectId, epoch: t.contextEpoch, loaded: t.loaded,
    selection: sel(), companion: useCompanion.getState().tabs, active: useCompanion.getState().activeTabId,
    pane: useWorkspace.getState().focusedPane, storage: Object.keys(window.localStorage).sort(),
  });
}

function publish(tree: ContextTree) {
  publishTree(tree, AT);
  const published = useContextTreeStore.getState().tree;
  if (published.status !== "ready") throw new Error(`fixture refused: ${published.error}`);
  return published;
}

const subproject = (id: string, route: string | null = `/inv/${id}`, label = `Question ${id}`): GearEffect =>
  ({ type: "select-subproject", id, route, label });

beforeEach(() => {
  const t = tabs();
  t.resetTabTrees();
  t.setTabTreeAdapter(createInMemoryTabTreeAdapter());
  t.selectProject(TAB_PROJECT_ID);
  clearTabProject();
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  render(<div data-pane="left" tabIndex={-1} /> );
  render(<div data-pane="right" tabIndex={-1} />);
});

afterEach(() => {
  cleanup();
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  clearTabProject();
  document.body.innerHTML = "";
});

describe("gear 1 — select-project", () => {
  it("dispatches PROJECT_SELECT_TOGGLE with the row to focus and changes no store", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    const seen: unknown[] = [];
    const onToggle = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
    const before = snapshot();
    const out = await runGearEffect({ type: "select-project", id: "p1" }, tree);
    window.removeEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
    expect(out).toEqual({ ok: true, changed: ["picker"] });
    expect(seen).toEqual([{ focusId: "p1" }]);
    expect(snapshot()).toBe(before);
    expect(tabs().projectId).toBe(TAB_PROJECT_ID);
  });
});

describe("gear 2 — select-subproject", () => {
  it("writes subProjectId and spawns exactly one research root; the companion and persistence are untouched", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    const storageBefore = Object.keys(window.localStorage).sort();
    const out = await runGearEffect(subproject("inv-root"), tree);
    expect(out).toEqual({ ok: true, changed: ["subproject", "tabs"] });
    expect(sel()).toEqual({ projectId: "default", subProjectId: "inv-root" });
    const research = tabs().trees.research!;
    expect(research.root_order).toEqual(["root:research:/inv/inv-root"]);
    expect(research.nodes["root:research:/inv/inv-root"]).toMatchObject({ kind: "research", ref: "/inv/inv-root" });
    expect(research.active_tab_id).toBe("root:research:/inv/inv-root");
    expect(tabs().navIntent).toMatchObject({ mothership: "research", tabId: "root:research:/inv/inv-root" });
    expect(useCompanion.getState().tabs).toEqual([]);
    expect(tabs().trees.reading).toBeNull();
    const added = Object.keys(window.localStorage).sort().filter((k) => !storageBefore.includes(k));
    expect(added.filter((k) => /sub-?project|selection|inv-root/i.test(k))).toEqual([]);
  });

  it("an investigation already open as a child tab is activated, never spawned as a second root", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    await tabs().ensureMothership("research");
    tabs().spawnTab("research", null, { tab_id: "root:research:/inv/other", kind: "research", ref: "/inv/other", mothership: "research", activate: true });
    tabs().spawnTab("research", "root:research:/inv/other", { tab_id: "child-1", kind: "research", ref: "/inv/inv-root", mothership: "research", activate: false });
    await act(async () => {});
    const out = await runGearEffect(subproject("inv-root"), tree);
    expect(out.ok).toBe(true);
    const research = tabs().trees.research!;
    expect(research.root_order).toEqual(["root:research:/inv/other"]);
    expect(research.active_tab_id).toBe("child-1");
    expect(Object.keys(research.nodes).sort()).toEqual(["child-1", "root:research:/inv/other"]);
  });

  it("the sub-project already selected still spawns its tab (the selection's false is not a refusal)", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    expect(useSelection.getState().selectSubProject("inv-root", tree)).toBe(true);
    expect(useSelection.getState().selectSubProject("inv-root", tree)).toBe(false);
    const out = await runGearEffect(subproject("inv-root"), tree);
    expect(out).toEqual({ ok: true, changed: ["subproject", "tabs"] });
    expect(tabs().trees.research!.root_order).toEqual(["root:research:/inv/inv-root"]);
  });

  it("issued across a project switch, it resolves after one epoch change and files the tab under the new project", async () => {
    const tree = publish(composePreBackendTree(fixtureInputsWithMembers()));
    const epoch = tabs().contextEpoch;
    const pending = runGearEffect(subproject("inv-root"), tree);
    useSelection.getState().selectProject("p1");
    expect(tabs().contextEpoch).toBe(epoch + 1);
    const out = await pending;
    expect(out.ok).toBe(true);
    expect(tabs().projectId).toBe("p1");
    expect(tabs().contextEpoch).toBe(epoch + 1);
    expect(tabs().trees.research!.root_order).toEqual(["root:research:/inv/inv-root"]);
    expect(sel()).toEqual({ projectId: "p1" });
  });

  it("a node without a route selects and spawns nothing ('no-route')", async () => {
    const base = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
    const p1 = base.roots.find((r) => r.id === "p1")!;
    const sp: ProjectNode = {
      id: "sp-1", kind: "subproject", title: "Sub one", parentId: "p1", children: [], agents: [],
      archived: false, provenance: "backend", source: { kind: "registry", project: project("sp-1", "Sub one") },
    };
    const tree = publish({ ...base, provenance: "backend", roots: [{ ...p1, provenance: "backend", children: [sp] }] });
    useSelection.getState().selectProject("p1");
    const out = await runGearEffect(subproject("sp-1", null, "Sub one"), tree);
    expect(out).toEqual({ ok: true, changed: ["subproject"], tab: "no-route" });
    expect(sel()).toEqual({ projectId: "p1", subProjectId: "sp-1" });
    expect(tabs().trees.research).toBeNull();
  });

  it("a stale tree is refused with zero writes", async () => {
    const composed = composePreBackendTree(fixtureInputs());
    const tree = publish({ ...composed, roots: composed.roots.filter((r) => r.id !== "default") });
    const before = snapshot();
    expect(await runGearEffect(subproject("inv-root"), tree)).toEqual({ ok: false, reason: "refused" });
    expect(await runGearEffect({ type: "select-agent", id: "inv-child", viewId: "agent:thread:inv-child", viewOpen: true, kind: "research-thread", investigationId: "inv-child", scope: "cross-project", label: "child thread" }, tree)).toEqual({ ok: false, reason: "refused" });
    expect(snapshot()).toBe(before);
  });
});

describe("gear 3 — select-agent", () => {
  it("an open agent: sets agentId, activates its companion tab, focuses the right pane; the trees are untouched", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    for (const a of tree.crossProjectAgents) useCompanion.getState().openAgentTab({ kind: a.kind, ...(a.investigationId ? { investigationId: a.investigationId } : {}), title: a.title });
    useCompanion.getState().activateAgentTab("agent:dialogue");
    useSelection.getState().selectSubProject("inv-root", tree);
    const treesBefore = JSON.stringify(tabs().trees);
    const out = await runGearEffect({ type: "select-agent", id: "inv-child", viewId: "agent:thread:inv-child", viewOpen: true, kind: "research-thread", investigationId: "inv-child", scope: "cross-project", label: "child thread" }, tree);
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(sel()).toEqual({ projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child");
    expect(useWorkspace.getState().focusedPane).toBe("right");
    expect(document.activeElement?.getAttribute("data-pane")).toBe("right");
    expect(JSON.stringify(tabs().trees)).toBe(treesBefore);
    expect(useCompanion.getState().tabs).toHaveLength(tree.crossProjectAgents.length);
  });

  it("a backend-shaped project-scoped dialogue with no open view cannot be opened: 'open-failed'", async () => {
    const base = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
    const p1 = base.roots.find((r) => r.id === "p1")!;
    const agent: AgentNode = {
      id: "agent:dialogue", viewId: "agent:dialogue", viewOpen: false, kind: "dialogue", runKind: "dialogue",
      scope: "project", scopeProvenance: "backend", projectId: "p1", title: "Dialogue", provenance: "backend",
    };
    const tree = publish({ ...base, provenance: "backend", roots: [{ ...p1, provenance: "backend", agents: [agent] }] });
    useSelection.getState().selectProject("p1");
    const out = await runGearEffect({ type: "select-agent", id: "agent:dialogue", viewId: "agent:dialogue", viewOpen: false, kind: "dialogue", scope: "project", label: "Dialogue" }, tree);
    expect(out).toEqual({ ok: false, reason: "open-failed" });
    expect(useCompanion.getState().tabs).toEqual([]);
  });

  it("a closed research view is opened through the contract's opener and becomes the active companion tab", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    // The companion holds no tab for inv-child: the tree says viewOpen, but
    // the effect carries what the model saw; use the opener path.
    const out = await runGearEffect({ type: "select-agent", id: "inv-child", viewId: "agent:thread:inv-child", viewOpen: false, kind: "research-thread", investigationId: "inv-child", scope: "cross-project", label: "child thread" }, tree);
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-child"]);
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child");
    expect(sel().agentId).toBe("inv-child");
  });
});
