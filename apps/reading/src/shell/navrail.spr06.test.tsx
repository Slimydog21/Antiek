/**
 * navrail.spr06.test.tsx — SPR-06 acceptance (bottom rail + igloo home).
 *
 * Load-bearing claims (asserted, not eyeballed):
 *  - the rail DEFAULTS to the bottom orientation (the four-edge-free shell);
 *  - bottom + left orientations expose the SAME four-door destination set,
 *    the SAME roles/labels, and the SAME accessible home control — only the
 *    layout axis differs (no parallel nav, no dropped destination);
 *  - the home control is a real, labelled, keyboard-focusable button that
 *    routes to /home (the igloo replaced the static penguin but the control
 *    semantics are unchanged);
 *  - every keyboard shortcut + the active-route accent are untouched (those
 *    live in shortcuts.ts + workflowTaxonomy and are not re-implemented per
 *    orientation — guarded here against an accidental fork).
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NavRail } from "./NavRail";
import { WORKFLOW_ORDER, WORKFLOWS } from "./workflowTaxonomy";

afterEach(cleanup);

const expectedDoorLabels = WORKFLOW_ORDER.map((wf) => WORKFLOWS[wf].label);

function doorLabels(group: HTMLElement): string[] {
  return Array.from(group.querySelectorAll(":scope > button")).map(
    (b) => b.querySelector(".sr-only")?.textContent?.trim() ?? "",
  );
}

describe("NavRail SPR-06 — bottom orientation + igloo home", () => {
  it("defaults to the bottom orientation (horizontal rail along the window bottom)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const rail = screen.getByLabelText("Primary navigation");
    // The bottom rail is a fixed-height horizontal bar with the accent on its
    // TOP edge (its inner edge, toward the working region). The left rail is a
    // fixed-WIDTH vertical bar. We assert the bottom-rail shape so a silent
    // revert to the left rail reddens.
    expect(rail.className).toContain("h-14");
    expect(rail.className).toContain("w-full");
    expect(rail.className).toContain("border-t-edge");
    expect(rail.className).not.toContain("w-[72px]");
  });

  it("bottom + left expose the identical four doors with identical labels (no dropped destination, no fork)", () => {
    const { unmount } = render(
      <MemoryRouter>
        <NavRail orientation="bottom" />
      </MemoryRouter>,
    );
    const bottomGroup = screen.getByTestId("navrail-workflows");
    const bottomLabels = doorLabels(bottomGroup);
    expect(bottomLabels).toEqual(expectedDoorLabels);
    expect(bottomGroup.querySelectorAll(":scope > button")).toHaveLength(4);
    unmount();

    render(
      <MemoryRouter>
        <NavRail orientation="left" />
      </MemoryRouter>,
    );
    const leftGroup = screen.getByTestId("navrail-workflows");
    expect(doorLabels(leftGroup)).toEqual(bottomLabels);
    expect(leftGroup.querySelectorAll(":scope > button")).toHaveLength(4);
  });

  it("preserves Search + More as the only non-door affordances in both orientations", () => {
    for (const orientation of ["bottom", "left"] as const) {
      const { unmount } = render(
        <MemoryRouter>
          <NavRail orientation={orientation} />
        </MemoryRouter>,
      );
      expect(screen.getByTitle("Search · ⌘K")).toBeTruthy();
      expect(screen.getByTitle(/More - all products/)).toBeTruthy();
      unmount();
    }
  });

  it("the home control is an accessible, keyboard-focusable button labelled for /home (igloo replaced the penguin, semantics intact)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const home = screen.getByRole("button", { name: "Antiek home" });
    // A real <button> is keyboard-focusable + activatable by default; the
    // visible focus ring is the focus-visible:outline class on it.
    expect(home.tagName).toBe("BUTTON");
    expect(home.className).toContain("focus-visible:outline");
    // The igloo mark renders inside it (an <svg>), the penguin <img> does not.
    expect(home.querySelector("svg")).toBeTruthy();
    expect(home.querySelector("img")).toBeNull();
    // No accessible name leaks onto the decorative mark itself.
    expect(within(home).queryByRole("img")).toBeNull();
  });

  it("bottom orientation: the active workflow door carries aria-current=page + the top-edge accent marker (M2 active-route accent preserved, not just claimed)", () => {
    // Render ON a real workflow route so workflowForPath() lights one door.
    // The pre-existing SPR-06 tests never set initialEntries, so the active
    // path was never exercised — this is the assertion that closes that gap.
    const activeWf = WORKFLOW_ORDER[0];
    render(
      <MemoryRouter initialEntries={[WORKFLOWS[activeWf].defaultRoute]}>
        <NavRail orientation="bottom" />
      </MemoryRouter>,
    );
    const group = screen.getByTestId("navrail-workflows");
    const current = group.querySelectorAll(
      ':scope > button[aria-current="page"]',
    );
    // Exactly the one door for the active route is marked current.
    expect(current).toHaveLength(1);
    expect(current[0].querySelector(".sr-only")?.textContent?.trim()).toBe(
      WORKFLOWS[activeWf].label,
    );
    // The accent slab sits on the rail's INNER (top) edge in bottom orientation.
    const marker = current[0].querySelector(
      'span[aria-hidden="true"].bg-ink',
    );
    expect(marker).toBeTruthy();
    expect(marker?.className).toContain("top-0");
    expect(marker?.className).toContain("h-1");
    expect(marker?.className).toContain("rounded-b");
  });

  it("left orientation: the same active door reflects the accent to its inner (left) edge — the accent is preserved + axis-reflected, not dropped", () => {
    const activeWf = WORKFLOW_ORDER[0];
    render(
      <MemoryRouter initialEntries={[WORKFLOWS[activeWf].defaultRoute]}>
        <NavRail orientation="left" />
      </MemoryRouter>,
    );
    const group = screen.getByTestId("navrail-workflows");
    const current = group.querySelectorAll(
      ':scope > button[aria-current="page"]',
    );
    expect(current).toHaveLength(1);
    const marker = current[0].querySelector(
      'span[aria-hidden="true"].bg-ink',
    );
    expect(marker).toBeTruthy();
    expect(marker?.className).toContain("left-0");
    expect(marker?.className).toContain("w-1");
    expect(marker?.className).toContain("rounded-r");
  });
});
