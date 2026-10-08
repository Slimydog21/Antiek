/**
 * selection.test.ts — SPR-06 M1/M3: the one selection store mirrors
 * tabTreeStore.projectId, is the one writer of the selected project, and
 * keeps sub/agent a prefix of a tree path.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, renderHook } from "@testing-library/react";

import { unitAccountKey } from "../../testAccountOwner";
import { clearTabProject, readTabProject } from "../persistence";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { composePreBackendTree } from "./adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers } from "./fixtures.test.helpers";
import { isSelectionPathOf, selectionPath, useIsSelected, useSelection } from "./selection";
import { findProjectPath } from "./tree";

const tabs = () => useTabTrees.getState();
const sel = () => useSelection.getState();

function resetProject() {
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  clearTabProject();
}

beforeEach(resetProject);
afterEach(() => { cleanup(); resetProject(); });

describe("S1 mirror", () => {
  it("follows tabTreeStore.selectProject and its epoch", () => {
    tabs().selectProject("p2");
    expect(sel().selection).toEqual({ projectId: "p2" });
    expect(sel().epoch).toBe(tabs().contextEpoch);
  });
});

describe("S2 the one writer", () => {
  it("persists through tabTreeStore and refuses blanks and no-ops", () => {
    const epoch0 = tabs().contextEpoch;
    expect(sel().selectProject("p2")).toBe(true);
    expect(readTabProject()).toBe("p2");
    expect(window.localStorage.getItem(unitAccountKey("antiek.workspace.tab-project"))).not.toBeNull();
    expect(tabs().projectId).toBe("p2");
    expect(tabs().contextEpoch).toBe(epoch0 + 1);
    expect(sel().selectProject("p2")).toBe(false);
    expect(tabs().contextEpoch).toBe(epoch0 + 1);
    expect(sel().selectProject("")).toBe(false);
    expect(sel().selectProject("   ")).toBe(false);
    expect(tabs().contextEpoch).toBe(epoch0 + 1);
    expect(readTabProject()).toBe("p2");
    expect(sel().selectProject("default")).toBe(true);
    expect(readTabProject()).toBeNull();
    expect(sel().selection).toEqual({ projectId: TAB_PROJECT_ID });
  });
});

describe("S3 the owner path", () => {
  it("a projectId written by setState clears sub/agent and notifies once", () => {
    const tree = composePreBackendTree(fixtureInputs());
    expect(sel().selectSubProject("inv-root", tree)).toBe(true);
    expect(sel().selectAgent("agent:dialogue", tree)).toBe(true);
    expect(sel().selection).toEqual({ projectId: "default", subProjectId: "inv-root", agentId: "agent:dialogue" });
    let calls = 0;
    const off = useSelection.subscribe(() => { calls += 1; });
    useTabTrees.setState({ projectId: "owner-b" });
    off();
    expect(calls).toBe(1);
    expect(sel().selection).toEqual({ projectId: "owner-b" });
  });
});

describe("S4 prefix invariant", () => {
  it("accepts only paths rooted at the selected project; agents on the path or cross-project", () => {
    const tree = composePreBackendTree(fixtureInputsWithMembers());
    // inv-member files under p1 via membership; the selection is default.
    expect(sel().selectSubProject("inv-member", tree)).toBe(false);
    expect(sel().selection).toEqual({ projectId: "default" });
    expect(isSelectionPathOf({ projectId: "default", subProjectId: "inv-member" }, tree)).toBe(false);
    expect(sel().selectSubProject("inv-child", tree)).toBe(true);
    expect(isSelectionPathOf(sel().selection, tree)).toBe(true);
    expect(selectionPath(sel().selection)).toEqual(["default", "inv-child"]);
    // A cross-project agent is selectable anywhere; a project-scoped one only on the path.
    expect(sel().selectAgent("agent:dialogue", tree)).toBe(true);
    expect(isSelectionPathOf(sel().selection, tree)).toBe(true);
    expect(sel().selectAgent("inv-member", tree)).toBe(false);
    expect(isSelectionPathOf({ projectId: "default", subProjectId: "inv-child", agentId: "inv-member" }, tree)).toBe(false);
    expect(sel().selection.agentId).toBe("agent:dialogue");
    // Switch to p1: the mirror clears, then the member path is accepted.
    expect(sel().selectProject("p1")).toBe(true);
    expect(sel().selection).toEqual({ projectId: "p1" });
    expect(sel().selectSubProject("inv-member", tree)).toBe(true);
    expect(sel().selectAgent("inv-member", tree)).toBe(true);
    expect(isSelectionPathOf(sel().selection, tree)).toBe(true);
    expect(selectionPath(sel().selection)).toEqual(["p1", "inv-member", "inv-member"]);
    // An unknown sub-project or agent is refused.
    expect(sel().selectSubProject("ghost", tree)).toBe(false);
    expect(sel().selectAgent("ghost", tree)).toBe(false);
    // null clears.
    expect(sel().selectAgent(null, tree)).toBe(true);
    expect(sel().selection).toEqual({ projectId: "p1", subProjectId: "inv-member" });
    expect(sel().selectSubProject(null, tree)).toBe(true);
    expect(sel().selection).toEqual({ projectId: "p1" });
  });
});

describe("S5 useIsSelected render isolation", () => {
  it("a selection move re-renders exactly the two rows that flip", () => {
    const renders = new Map<string, number>();
    function Row({ id }: { id: string }) {
      renders.set(id, (renders.get(id) ?? 0) + 1);
      const on = useIsSelected(id, "project");
      return <li data-on={on ? "1" : "0"}>{id}</li>;
    }
    const ids = Array.from({ length: 500 }, (_, i) => `p${i + 1}`);
    render(<ul>{ids.map((id) => <Row key={id} id={id} />)}</ul>);
    act(() => { sel().selectProject("p1"); });
    const before = new Map(renders);
    act(() => { sel().selectProject("p2"); });
    const changed = ids.filter((id) => renders.get(id) !== before.get(id));
    expect(changed).toEqual(["p1", "p2"]);
    expect(renders.get("p1")).toBe(before.get("p1")! + 1);
    expect(renders.get("p2")).toBe(before.get("p2")! + 1);
  });
});

describe("S6 useIsSelected is keyed by role", () => {
  it("a selected agent never lights the sibling sub-project row that shares its id", () => {
    const tree = composePreBackendTree(fixtureInputs());
    expect(sel().selectSubProject("inv-child-2", tree)).toBe(true);
    expect(sel().selectAgent("inv-child", tree)).toBe(true);
    expect(sel().selection).toEqual({ projectId: "default", subProjectId: "inv-child-2", agentId: "inv-child" });
    // Pre-backend the research agent's id IS the investigation id, and a
    // sibling sub-project node carries that same id off the selected path.
    expect(findProjectPath(tree, "inv-child")!.map((n) => n.id)).toEqual(["default", "inv-root", "inv-child"]);
    const asSub = renderHook(() => useIsSelected("inv-child", "subproject"));
    const asAgent = renderHook(() => useIsSelected("inv-child", "agent"));
    const asProject = renderHook(() => useIsSelected("inv-child", "project"));
    expect(asSub.result.current).toBe(false);
    expect(asAgent.result.current).toBe(true);
    expect(asProject.result.current).toBe(false);
    // The lit sub-project rows are exactly the selection path's sub-project.
    const lit = ["inv-root", "inv-child", "inv-child-2", "inv-orphan"].filter((id) => renderHook(() => useIsSelected(id, "subproject")).result.current);
    expect(lit).toEqual(["inv-child-2"]);
    expect(renderHook(() => useIsSelected("default", "project")).result.current).toBe(true);
    expect(renderHook(() => useIsSelected("default", "subproject")).result.current).toBe(false);
    expect(renderHook(() => useIsSelected("default", "agent")).result.current).toBe(false);
    // Clearing the agent flips only the agent answer.
    act(() => { sel().selectAgent(null, tree); });
    expect(asAgent.result.current).toBe(false);
    expect(asSub.result.current).toBe(false);
  });
});
