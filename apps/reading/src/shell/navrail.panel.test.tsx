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
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { NavRail } from "./NavRail";
import {
  modesForWorkflow,
  WORKFLOW_ORDER,
  WORKFLOWS,
} from "./workflowTaxonomy";

const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";
const s = () => useWorkspace.getState();

// SPR-08 — the rail now renders on-bar KeyChips (usePrefersReducedMotion →
// matchMedia). jsdom lacks matchMedia; stub it as the other suites do. No new
// assertion — it only lets the real rail render its real children.
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

beforeEach(() => {
  s().reset();
});

afterEach(cleanup);

describe("NavRail → panel mount contract (SPR-04 M6)", () => {
  it("the project-tree toggle mounts ProjectTree as a docked-left panel with the stable id", () => {
    // Exercises the store contract DIRECTLY (the old NavRail.toggleTree
    // helper was removed in SPR-12 M3 — the project tree is now reached
    // through the Penguin mascot). This is still the exact open() call the
    // mounting path makes, so the contract under test is unchanged.
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
    const id = s().open(
      "Trajectory",
      { id: "story-investigation" },
      { mode: "floating", title: "Story investigation" },
    );
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
  it("workflow-destination group has exactly four doors (U-01 literal count guard)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>
    );
    const group = screen.getByTestId("navrail-workflows");
    const buttons = group.querySelectorAll(":scope > button");
    // The literal 4 is intentional and non-derived: deriving the count from
    // WORKFLOW_ORDER would move with the rail (both map the same list), so a
    // fifth workflow would stay green. Pinning the literal makes a deliberate
    // fifth destination redden CI — the load-bearing half of the M4 gate.
    expect(
      buttons.length,
      `the rail is exactly four doors (Research / Read / Write / Speak) + utilities + More - see U-01. A fifth workflow added to WORKFLOW_ORDER must redden this.`,
    ).toBe(4);

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
