import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Roadmap } from "./Roadmap";
import type { RoadmapView, SprintView } from "./Roadmap";

afterEach(() => {
  cleanup();
});

function sprint(n: number, blockedOn: string[], unblocked = false): SprintView {
  return {
    spec: "read",
    spec_label: "Read",
    sprint: n,
    slug: `read-sprint-${n}`,
    node_id: `read:${n}`,
    status: "unknown",
    on_critical_path: false,
    blocked_on: blockedOn,
    unblocked,
  };
}

function roadmap(sprints: SprintView[], unblockedNow: string[] = []): RoadmapView {
  return {
    total_sprints: sprints.length,
    superseded_count: 0,
    superseded_note: "",
    reconciliation: `Read ${sprints.length} = ${sprints.length}`,
    critical_path: [],
    rosters: [
      {
        spec: "read",
        label: "Read",
        directory: "read",
        count: sprints.length,
        sprints,
      },
    ],
    unblocked_now: unblockedNow,
    substrate_layers: [],
  };
}

describe("Roadmap", () => {
  it("renders dependency-ready empty state and blocker summary", () => {
    render(<Roadmap roadmap={roadmap([sprint(1, ["drw:5"])])} />);

    expect(
      screen.getByText("0 dependency-ready · 1 blocked by dependency state"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "No sprint is dependency-ready under the current dependency state.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Dependency blockers")).toBeTruthy();
    expect(screen.getByText("drw:5")).toBeTruthy();
    expect(screen.getByText("Read · SPR-01")).toBeTruthy();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(screen.getByText("waits on drw:5")).toBeTruthy();
  });

  it("omits dependency blockers when every sprint is dependency-ready", () => {
    render(<Roadmap roadmap={roadmap([sprint(1, [], true)], ["read:1"])} />);

    expect(
      screen.getByText("1 dependency-ready · 0 blocked by dependency state"),
    ).toBeTruthy();
    expect(screen.queryByText("Dependency blockers")).toBeNull();
  });

  it("sorts blocker fan-out, truncates samples, and dedupes duplicate waits", () => {
    render(
      <Roadmap
        roadmap={roadmap([
          sprint(1, ["drw:5", "drw:5"]),
          sprint(2, ["drw:5"]),
          sprint(3, ["drw:5"]),
          sprint(4, ["drw:5"]),
          sprint(5, ["drw:6"]),
        ])}
      />,
    );

    const text = document.body.textContent ?? "";
    expect(text.indexOf("drw:5")).toBeLessThan(text.indexOf("drw:6"));
    expect(screen.getByText("blocks 4 sprints")).toBeTruthy();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(
      screen.getByText("Read · SPR-01, Read · SPR-02, Read · SPR-03 +1 more"),
    ).toBeTruthy();
  });
});
