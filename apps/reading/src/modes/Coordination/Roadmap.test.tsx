import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Roadmap } from "./Roadmap";
import type { RoadmapView } from "./Roadmap";

afterEach(() => {
  cleanup();
});

describe("Roadmap", () => {
  it("renders an explicit dependency-ready empty state", () => {
    const roadmap: RoadmapView = {
      total_sprints: 1,
      superseded_count: 0,
      superseded_note: "",
      reconciliation: "Read 1 = 1",
      critical_path: [],
      rosters: [
        {
          spec: "read",
          label: "Read",
          directory: "read",
          count: 1,
          sprints: [
            {
              spec: "read",
              spec_label: "Read",
              sprint: 1,
              slug: "blocked-reader",
              node_id: "read:1",
              status: "unknown",
              on_critical_path: false,
              blocked_on: ["drw:5"],
              unblocked: false,
            },
          ],
        },
      ],
      unblocked_now: [],
      substrate_layers: [],
    };

    render(<Roadmap roadmap={roadmap} />);

    expect(
      screen.getByText("0 dependency-ready · 1 blocked by dependency state"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "No sprint is dependency-ready under the current dependency state.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("waits on drw:5")).toBeTruthy();
  });
});
