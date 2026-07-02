import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Roadmap } from "./Roadmap";
import type { DependencyBlockerView, RoadmapView, SprintView } from "./Roadmap";

afterEach(() => {
  cleanup();
});

function sprint(
  n: number,
  blockedOn: string[],
  unblocked = false,
  spec: "drw" | "read" = "read",
): SprintView {
  return {
    spec,
    spec_label: spec === "drw" ? "Research (DRW)" : "Read",
    sprint: n,
    slug: spec === "drw" && n === 5 ? "cascade-planner" : `${spec}-sprint-${n}`,
    node_id: `${spec}:${n}`,
    status: spec === "drw" ? "planned" : "unknown",
    on_critical_path: false,
    blocked_on: blockedOn,
    unblocked,
  };
}

function roadmap(
  sprints: SprintView[],
  unblockedNow: string[] = [],
  dependencyBlockers: DependencyBlockerView[] = [],
): RoadmapView {
  const specs: Array<"drw" | "read"> = ["drw", "read"];
  return {
    total_sprints: sprints.length,
    superseded_count: 0,
    superseded_note: "",
    reconciliation: `Read ${sprints.length} = ${sprints.length}`,
    critical_path: [],
    rosters: specs.flatMap((spec) => {
      const rows = sprints.filter((s) => s.spec === spec);
      if (rows.length === 0) return [];
      return [
        {
          spec,
          label: spec === "drw" ? "Research (DRW)" : "Read",
          directory: spec === "drw" ? "deep-research-workspace" : "read",
          count: rows.length,
          sprints: rows,
        },
      ];
    }),
    unblocked_now: unblockedNow,
    dependency_blockers: dependencyBlockers,
    substrate_layers: [],
  };
}

describe("Roadmap", () => {
  it("renders dependency-ready empty state and blocker summary", () => {
    render(
      <Roadmap
        roadmap={roadmap([
          sprint(5, [], true, "drw"),
          sprint(1, ["drw:5"]),
        ])}
      />,
    );

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
    expect(
      screen.getByText("Research (DRW) · SPR-05 · cascade planner · planned"),
    ).toBeTruthy();
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
        roadmap={roadmap(
          [
            sprint(5, [], true, "drw"),
            sprint(6, [], true, "drw"),
            sprint(1, ["drw:5", "drw:5"]),
            sprint(2, ["drw:5"]),
            sprint(3, ["drw:5"]),
            sprint(4, ["drw:5"]),
            sprint(5, ["drw:6"]),
          ],
          [],
          [
            { node_id: "drw:6", blocked_sprints: ["read:5"] },
            {
              node_id: "drw:5",
              blocked_sprints: [
                "read:1",
                "read:1",
                "read:2",
                "read:3",
                "read:4",
              ],
            },
            { node_id: "missing:9", blocked_sprints: ["read:1"] },
          ],
        )}
      />,
    );

    const text = document.body.textContent ?? "";
    expect(text.indexOf("drw:5")).toBeLessThan(text.indexOf("drw:6"));
    expect(screen.getByText("blocks 4 sprints")).toBeTruthy();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(
      screen.getByText("Research (DRW) · SPR-05 · cascade planner · planned"),
    ).toBeTruthy();
    expect(
      screen.getByText("Read · SPR-01, Read · SPR-02, Read · SPR-03 +1 more"),
    ).toBeTruthy();
  });

  it("falls back to roster truth when API blockers are partial or duplicated", () => {
    render(
      <Roadmap
        roadmap={roadmap(
          [
            sprint(1, ["drw:5"]),
            sprint(2, ["drw:5"]),
            sprint(3, ["drw:6"]),
          ],
          [],
          [
            { node_id: "drw:5", blocked_sprints: ["read:1"] },
            { node_id: "drw:5", blocked_sprints: ["read:2"] },
          ],
        )}
      />,
    );

    expect(screen.getAllByText("blocks 2 sprints")).toHaveLength(1);
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(screen.getByText("Read · SPR-01, Read · SPR-02")).toBeTruthy();
    expect(screen.getByText("Read · SPR-03")).toBeTruthy();
  });
});
