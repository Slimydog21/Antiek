/**
 * gearActions.test.tsx — SPR-04 M4: selecting at each gear changes exactly
 * the expected store and no other, on the REAL stores (the in-memory tab
 * tree adapter, useSelection, the context tree store via publishTree,
 * useCompanion, useWorkspace). "No other" is checked mechanically: every
 * zustand store in apps/reading/src (12) is subscribed and the set that
 * changed is asserted exactly (repair round 2026-10-07T22:40Z). Rigor #4:
 * selectProject RESETS the trees (tabTreeStore.ts:514-527), so a spawn
 * issued across a switch must land under the new project, not die silently.
 *
 * The effect reads the stores' CURRENT tree (useContextTreeStore), never a
 * snapshot: a tree published between keypress and effect is the one that
 * admits or refuses the write.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { usePinned } from "../../components/navigation/pinnedStore";
import { useReadingStateBus } from "../../hooks/useReadingState";
import { useBlockSources } from "../blockSources";
import { useCompanion } from "../companionStore";
import { COMPANION_PANEL_ID } from "../companionVisibility";
import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers, project, tab as fixtureTab } from "../contracts/fixtures.test.helpers";
import { useSelection } from "../contracts/selection";
import type { AgentNode, ContextTree, ProjectNode } from "../contracts/tree";
import { publishTree, useContextTreeStore } from "../contracts/treeStore";
import { useForkLineage } from "../forkLineage";
import { clearTabProject } from "../persistence";
import { SHORTCUT_EVENTS } from "../shortcuts";
import { createInMemoryTabTreeAdapter } from "../tabTree";
import { useTabTitles } from "../tabTitles";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { useWindows } from "../windowsStore";
import { useWorkspace } from "../WorkspaceStore";
import { useWriteOutline } from "../writeOutlineStore";
import { runGearEffect } from "./gearActions";
import type { GearEffect } from "./switcherKeys";

const AT = "2026-10-07T22:40:00Z";
const tabs = () => useTabTrees.getState();
const sel = () => useSelection.getState().selection;

/** Every zustand store under apps/reading/src. A new store belongs here. */
const ALL_STORES = {
  selection: useSelection, tabTrees: useTabTrees, contextTree: useContextTreeStore, companion: useCompanion,
  workspace: useWorkspace, forkLineage: useForkLineage, writeOutline: useWriteOutline, blockSources: useBlockSources,
  windows: useWindows, tabTitles: useTabTitles, pinned: usePinned, readingStateBus: useReadingStateBus,
} as const;
type Watched = { subscribe: (fn: (s: Record<string, unknown>, p: Record<string, unknown>) => void) => () => void };

/** Which stores' non-function state changed while `fn` ran. */
async function storesChangedBy<T>(fn: () => Promise<T>): Promise<{ out: T; stores: string[] }> {
  const changed = new Set<string>();
  const unsubs = Object.entries(ALL_STORES).map(([name, store]) =>
    (store as Watched).subscribe((s, p) => {
      if (Object.keys(s).some((k) => typeof s[k] !== "function" && s[k] !== p[k])) changed.add(name);
    }));
  try {
    const out = await fn();
    return { out, stores: [...changed].sort() };
  } finally {
    unsubs.forEach((u) => u());
  }
}

function publish(tree: ContextTree) {
  publishTree(tree, AT);
  const published = useContextTreeStore.getState().tree;
  if (published.status !== "ready") throw new Error(`fixture refused: ${published.error}`);
  return published;
}

const subproject = (id: string, route: string | null = `/inv/${id}`, label = `Question ${id}`): GearEffect =>
  ({ type: "select-subproject", id, route, label });
const CHILD_THREAD: GearEffect = { type: "select-agent", id: "inv-child", viewId: "agent:thread:inv-child", viewOpen: true, kind: "research-thread", investigationId: "inv-child", scope: "cross-project", label: "child thread" };

function openCompanionTabs(tree: ContextTree) {
  for (const a of tree.crossProjectAgents) useCompanion.getState().openAgentTab({ kind: a.kind, ...(a.investigationId ? { investigationId: a.investigationId } : {}), title: a.title });
}

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
    publish(composePreBackendTree(fixtureInputs()));
    const seen: unknown[] = [];
    const onToggle = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
    const { out, stores } = await storesChangedBy(() => runGearEffect({ type: "select-project", id: "p1" }));
    window.removeEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
    expect(out).toEqual({ ok: true, changed: ["picker"] });
    expect(seen).toEqual([{ focusId: "p1" }]);
    expect(stores).toEqual([]);
    expect(tabs().projectId).toBe(TAB_PROJECT_ID);
  });
});

describe("gear 2 — select-subproject", () => {
  it("writes subProjectId and spawns exactly one research root; the stores that change are selection, tabTrees and the tabTitles cache, no other", async () => {
    publish(composePreBackendTree(fixtureInputs()));
    const storageBefore = Object.keys(window.localStorage).sort();
    const { out, stores } = await storesChangedBy(() => runGearEffect(subproject("inv-root")));
    expect(out).toEqual({ ok: true, changed: ["subproject", "tabs"] });
    expect(stores).toEqual(["selection", "tabTitles", "tabTrees"]);
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
    publish(composePreBackendTree(fixtureInputs()));
    await tabs().ensureMothership("research");
    tabs().spawnTab("research", null, { tab_id: "root:research:/inv/other", kind: "research", ref: "/inv/other", mothership: "research", activate: true });
    tabs().spawnTab("research", "root:research:/inv/other", { tab_id: "child-1", kind: "research", ref: "/inv/inv-root", mothership: "research", activate: false });
    await act(async () => {});
    const { out, stores } = await storesChangedBy(() => runGearEffect(subproject("inv-root")));
    expect(out.ok).toBe(true);
    expect(stores).toEqual(["selection", "tabTrees"]);
    const research = tabs().trees.research!;
    expect(research.root_order).toEqual(["root:research:/inv/other"]);
    expect(research.active_tab_id).toBe("child-1");
    expect(Object.keys(research.nodes).sort()).toEqual(["child-1", "root:research:/inv/other"]);
  });

  it("the sub-project already selected still spawns its tab (the selection's false is not a refusal)", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    expect(useSelection.getState().selectSubProject("inv-root", tree)).toBe(true);
    expect(useSelection.getState().selectSubProject("inv-root", tree)).toBe(false);
    const out = await runGearEffect(subproject("inv-root"));
    expect(out).toEqual({ ok: true, changed: ["subproject", "tabs"] });
    expect(tabs().trees.research!.root_order).toEqual(["root:research:/inv/inv-root"]);
  });

  it("issued across a project switch, it resolves after one epoch change and files the tab under the new project", async () => {
    publish(composePreBackendTree(fixtureInputsWithMembers()));
    const epoch = tabs().contextEpoch;
    const pending = runGearEffect(subproject("inv-root"));
    useSelection.getState().selectProject("p1");
    expect(tabs().contextEpoch).toBe(epoch + 1);
    const out = await pending;
    expect(out.ok).toBe(true);
    expect(tabs().projectId).toBe("p1");
    expect(tabs().contextEpoch).toBe(epoch + 1);
    expect(tabs().trees.research!.root_order).toEqual(["root:research:/inv/inv-root"]);
    expect(sel()).toEqual({ projectId: "p1" });
  });

  it("a node without a route selects and spawns nothing ('no-route'): only the selection changes", async () => {
    const base = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
    const p1 = base.roots.find((r) => r.id === "p1")!;
    const sp: ProjectNode = {
      id: "sp-1", kind: "subproject", title: "Sub one", parentId: "p1", children: [], agents: [],
      archived: false, provenance: "backend", source: { kind: "registry", project: project("sp-1", "Sub one") },
    };
    publish({ ...base, provenance: "backend", roots: [{ ...p1, provenance: "backend", children: [sp] }] });
    useSelection.getState().selectProject("p1");
    const { out, stores } = await storesChangedBy(() => runGearEffect(subproject("sp-1", null, "Sub one")));
    expect(out).toEqual({ ok: true, changed: ["subproject"], tab: "no-route" });
    expect(stores).toEqual(["selection"]);
    expect(sel()).toEqual({ projectId: "p1", subProjectId: "sp-1" });
    expect(tabs().trees.research).toBeNull();
  });

  it("a stale tree is refused with zero writes", async () => {
    const composed = composePreBackendTree(fixtureInputs());
    publish({ ...composed, roots: composed.roots.filter((r) => r.id !== "default") });
    const { out, stores } = await storesChangedBy(async () => [
      await runGearEffect(subproject("inv-root")),
      await runGearEffect(CHILD_THREAD),
    ]);
    expect(out).toEqual([{ ok: false, reason: "refused" }, { ok: false, reason: "refused" }]);
    expect(stores).toEqual([]);
  });
});

describe("gear 3 — select-agent", () => {
  it("an open agent: sets agentId, activates its companion tab, focuses the right pane; companion + selection + workspace change, no other", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    openCompanionTabs(tree);
    useCompanion.getState().activateAgentTab("agent:dialogue");
    useSelection.getState().selectSubProject("inv-root", tree);
    const treesBefore = JSON.stringify(tabs().trees);
    const { out, stores } = await storesChangedBy(() => runGearEffect(CHILD_THREAD));
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(stores).toEqual(["companion", "selection", "workspace"]);
    expect(sel()).toEqual({ projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child");
    expect(useWorkspace.getState().focusedPane).toBe("right");
    expect(document.activeElement?.getAttribute("data-pane")).toBe("right");
    expect(JSON.stringify(tabs().trees)).toBe(treesBefore);
    expect(useCompanion.getState().tabs).toHaveLength(tree.crossProjectAgents.length);
  });

  it("a backend-shaped project-scoped dialogue with no open view cannot be opened: 'open-failed' with ZERO writes", async () => {
    const base = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
    const p1 = base.roots.find((r) => r.id === "p1")!;
    const agent: AgentNode = {
      id: "agent:dialogue", viewId: "agent:dialogue", viewOpen: false, kind: "dialogue", runKind: "dialogue",
      scope: "project", scopeProvenance: "backend", projectId: "p1", title: "Dialogue", provenance: "backend",
    };
    publish({ ...base, provenance: "backend", roots: [{ ...p1, provenance: "backend", agents: [agent] }] });
    useSelection.getState().selectProject("p1");
    const { out, stores } = await storesChangedBy(() =>
      runGearEffect({ type: "select-agent", id: "agent:dialogue", viewId: "agent:dialogue", viewOpen: false, kind: "dialogue", scope: "project", label: "Dialogue" }));
    expect(out).toEqual({ ok: false, reason: "open-failed" });
    expect(stores).toEqual([]);
    expect(useCompanion.getState().tabs).toEqual([]);
    expect(sel()).toEqual({ projectId: "p1" });
  });

  it("a closed research view is opened through the contract's opener and becomes the active companion tab", async () => {
    publish(composePreBackendTree(fixtureInputs()));
    // The companion holds no tab for inv-child: the tree says viewOpen, but
    // the companion's own list decides; use the opener path.
    const { out, stores } = await storesChangedBy(() => runGearEffect({ ...CHILD_THREAD, viewOpen: false }));
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(stores).toEqual(["companion", "selection", "workspace"]);
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual(["agent:thread:inv-child"]);
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child");
    expect(sel().agentId).toBe("inv-child");
  });

  it("the effect's viewOpen is stale (the companion tab closed after the model read it): the tab is reopened, never a phantom 'companion' change", async () => {
    const tree = publish(composePreBackendTree(fixtureInputs()));
    openCompanionTabs(tree);
    useCompanion.getState().activateAgentTab("agent:dialogue");
    useSelection.getState().selectSubProject("inv-root", tree);
    useCompanion.getState().closeAgentTab("agent:thread:inv-child");
    const { out, stores } = await storesChangedBy(() => runGearEffect(CHILD_THREAD)); // viewOpen: true, a lie by now
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(stores).toEqual(["companion", "selection", "workspace"]);
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:inv-child");
    expect(sel()).toEqual({ projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
  });

  it("the tree is read from the store at run time: an agent that left the tree between keypress and effect is refused with zero writes", async () => {
    const t = fixtureTab("research-thread", { investigationId: "inv-gone-soon", title: "x" });
    publish(composePreBackendTree(fixtureInputs({ companionTabs: [t] })));
    // The tab closes; the feeder republishes (reconcile runs here) before the microtask effect.
    publish(composePreBackendTree(fixtureInputs({ companionTabs: [] })));
    const { out, stores } = await storesChangedBy(() =>
      runGearEffect({ type: "select-agent", id: "inv-gone-soon", viewId: t.id, viewOpen: true, kind: "research-thread", investigationId: "inv-gone-soon", scope: "cross-project", label: "x" }));
    expect(out).toEqual({ ok: false, reason: "refused" });
    expect(stores).toEqual([]);
    expect(sel()).toEqual({ projectId: "default" });
  });

  it("docked preset: gear 3 focuses the companion dock panel (never cycles to the next panel), whether or not a panel was focused", async () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const tree = publish(composePreBackendTree(fixtureInputs()));
    useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left", id: "outline-x", title: "Outline" });
    openCompanionTabs(tree); // surfaces companion:main in the right dock
    expect(useWorkspace.getState().dockRightIds).toEqual([COMPANION_PANEL_ID]);
    useWorkspace.getState().focus(COMPANION_PANEL_ID);
    useSelection.getState().selectSubProject("inv-root", tree);
    const first = await storesChangedBy(() => runGearEffect(CHILD_THREAD));
    expect(first.out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(first.stores).toEqual(["companion", "selection"]); // already focused: the workspace store is untouched
    expect(useWorkspace.getState().focusedPanelId).toBe(COMPANION_PANEL_ID);
    useWorkspace.setState({ focusedPanelId: null });
    useCompanion.getState().activateAgentTab("agent:dialogue");
    const second = await storesChangedBy(() => runGearEffect(CHILD_THREAD));
    expect(second.stores).toEqual(["companion", "workspace"]); // the selection already names inv-child
    expect(useWorkspace.getState().focusedPanelId).toBe(COMPANION_PANEL_ID);
    expect(useWorkspace.getState().focusedPane).toBeNull();
  });

  it("docked preset with the companion panel closed: gear 3 surfaces it in the right dock and focuses it", async () => {
    useWorkspace.getState().setLayoutPreset("docked");
    const tree = publish(composePreBackendTree(fixtureInputs()));
    openCompanionTabs(tree);
    useWorkspace.getState().close(COMPANION_PANEL_ID);
    useSelection.getState().selectSubProject("inv-root", tree);
    const { out } = await storesChangedBy(() => runGearEffect(CHILD_THREAD));
    expect(out).toEqual({ ok: true, changed: ["agent", "companion"] });
    expect(useWorkspace.getState().dockRightIds).toEqual([COMPANION_PANEL_ID]);
    expect(useWorkspace.getState().focusedPanelId).toBe(COMPANION_PANEL_ID);
  });
});
