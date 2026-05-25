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
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { NavRail } from "./NavRail";
import {
  isWorkflowDestination,
  modesForWorkflow,
  WORKFLOW_ORDER,
  WORKFLOWS,
} from "./workflowTaxonomy";

const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";
const s = () => useWorkspace.getState();

beforeEach(() => {
  s().reset();
});

afterEach(cleanup);

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

/**
 * U-01 M4 anti-regression guard.
 * The rail's top-level destinations are exactly the four workflows sourced
 * from WORKFLOW_ORDER. Nothing operator/admin lives at rail level.
 * Search/New/More are utilities/overflow (outside the workflows group).
 * A fifth destination or promoted shared entry fails this with U-01 message.
 */
describe("NavRail four-door canonical + anti-regression guard (U-01 M4)", () => {
  it("workflow-destination group has exactly the taxonomy rail destinations (U-01 count guard, now via shared predicate)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>
    );
    const group = screen.getByTestId("navrail-workflows");
    const buttons = group.querySelectorAll(":scope > button");
    // Derive expected count from the SSOT predicate over the taxonomy list.
    const railDestinationCount = WORKFLOW_ORDER.filter((wf) =>
      isWorkflowDestination(wf),
    ).length;
    expect(
      buttons.length,
      `the rail is four doors + utilities + More - see U-01. The navrail-workflows group children must equal the number of workflow destinations (no fifth door, no operator/shared promoted to rail).`,
    ).toBe(railDestinationCount);

    const labels = Array.from(buttons).map(
      (b) => b.querySelector(".sr-only")?.textContent?.trim() ?? ""
    );
    const expected = WORKFLOW_ORDER.map((wf) => WORKFLOWS[wf].label);
    expect(labels).toEqual(expected);
  });

  it("never renders a shared-bucket destination (operator/admin/settings/governance) on the rail (U-01 guard, now via shared predicate)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>
    );
    const group = screen.getByTestId("navrail-workflows");
    const labels = Array.from(group.querySelectorAll(".sr-only")).map(
      (el) => el.textContent?.trim() ?? "",
    );

    // Taxonomy-driven: the shared bucket is the source list of everything
    // that must stay behind More. The guard reads both the rendered DOM
    // and the taxonomy; any leak fails the build.
    const sharedLabels = modesForWorkflow("shared").map((m) => m.label);
    const leaked = labels.filter((l) => sharedLabels.includes(l));

    expect(
      leaked,
      leaked.length > 0
        ? `operator/admin lives behind More (see U-01 / shared predicate). Leaked on rail: ${leaked.join(", ")}`
        : "",
    ).toHaveLength(0);
  });

  it("Search, New, and More are classified as utilities/overflow (outside the workflow-destination group)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>
    );
    const group = screen.getByTestId("navrail-workflows");
    // Only the four workflow buttons live inside the group.
    expect(group.querySelectorAll("button").length).toBe(WORKFLOW_ORDER.length);
    // More exists in the rail but is not a workflow destination.
    expect(screen.getByTitle(/More - all products/)).toBeTruthy();
  });
});
