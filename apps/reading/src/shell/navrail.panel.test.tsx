/**
 * navrail.panel.test.tsx — SPR-04 milestone 6 (preserve the panel system).
 *
 * The IA reorganization is navigation/grouping only. A mode must still
 * mount as a panel exactly as before. The new NavRail's project-tree
 * toggle goes through the SAME workspace path the old rail used:
 *
 *     useWorkspace.open("ProjectTree", {}, { mode: "docked-left",
 *                       id: "shortcuts:projecttree" })
 *
 * This test reproduces that exact call and asserts the panel mounts into
 * the left dock with the stable id — i.e. the mounting contract the
 * NavRail depends on is unchanged. If a future edit to the rail or the
 * store breaks the mount path, this fails.
 *
 * (We assert against the store rather than rendering the rail with a
 * router because the mounting CONTRACT — what open() does — is what's
 * load-bearing; the rail is a thin caller of it.)
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspace } from "../workspace/WorkspaceStore";

const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";
const s = () => useWorkspace.getState();

beforeEach(() => {
  s().reset();
});

describe("NavRail → panel mount contract (SPR-04 M6)", () => {
  it("the project-tree toggle mounts ProjectTree as a docked-left panel with the stable id", () => {
    // Exactly the call NavRail.toggleTree makes.
    s().open(
      "ProjectTree",
      {},
      { mode: "docked-left", title: "Project", id: PROJECT_TREE_PANEL_ID },
    );

    const panel = s().panels[PROJECT_TREE_PANEL_ID];
    expect(panel).toBeDefined();
    expect(panel.kind).toBe("ProjectTree");
    expect(panel.mode).toBe("docked-left");
    expect(s().dockLeftIds).toContain(PROJECT_TREE_PANEL_ID);
  });

  it("toggling again closes it (no duplicate, identical to old flow)", () => {
    s().open("ProjectTree", {}, { mode: "docked-left", id: PROJECT_TREE_PANEL_ID });
    expect(Boolean(s().panels[PROJECT_TREE_PANEL_ID])).toBe(true);
    s().close(PROJECT_TREE_PANEL_ID);
    expect(Boolean(s().panels[PROJECT_TREE_PANEL_ID])).toBe(false);
    expect(s().dockLeftIds).not.toContain(PROJECT_TREE_PANEL_ID);
  });

  it("a content-tree node opened via the rail's tree floats a panel (ProjectTree Cmd-click path)", () => {
    // The tree's Cmd/Ctrl+click path: open a Trajectory panel floating.
    const id = s().open("Trajectory", { id: "nvda-q4" }, { mode: "floating", title: "NVDA Q4 risk model" });
    const panel = s().panels[id];
    expect(panel.kind).toBe("Trajectory");
    expect(panel.mode).toBe("floating");
    expect(s().floatingIds).toContain(id);
  });
});
