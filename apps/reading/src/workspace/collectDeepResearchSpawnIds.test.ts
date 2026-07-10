import { describe, expect, it } from "vitest";
import { collectDeepResearchSpawnIds } from "./collectDeepResearchSpawnIds";
import { DEEP_RESEARCH_WINDOW_KIND } from "./deepResearchWindow";
import type { WorkspaceWindowDescriptor } from "./windowsStore";

function win(
  id: string,
  kind: string,
  spawn_id?: string,
): WorkspaceWindowDescriptor {
  return {
    id,
    kind: kind as WorkspaceWindowDescriptor["kind"],
    mode: "floating",
    z: 1,
    rect: { x: 0, y: 0, width: 100, height: 100 },
    title: id,
    payload: spawn_id ? { spawn_id } : {},
  };
}

describe("collectDeepResearchSpawnIds", () => {
  it("includes current spawn and de-dupes", () => {
    const ids = collectDeepResearchSpawnIds({
      currentSpawnId: "spn_a",
      extraSpawnIds: ["spn_a", "spn_b"],
    });
    expect(ids).toEqual(["spn_a", "spn_b"]);
  });

  it("collects spawn ids from open deep_research_session windows only", () => {
    const windows = {
      w1: win("w1", DEEP_RESEARCH_WINDOW_KIND, "spn_open_1"),
      w2: win("w2", "library", "spn_ignore"),
      w3: win("w3", DEEP_RESEARCH_WINDOW_KIND, "spn_open_2"),
    };
    const ids = collectDeepResearchSpawnIds({
      currentSpawnId: "spn_current",
      windows,
    });
    expect(ids).toEqual(["spn_current", "spn_open_1", "spn_open_2"]);
  });

  it("returns empty when no real spawn ids exist", () => {
    expect(collectDeepResearchSpawnIds({})).toEqual([]);
    expect(collectDeepResearchSpawnIds({ currentSpawnId: "  " })).toEqual([]);
  });

  it("double-run is stable", () => {
    const source = {
      currentSpawnId: "spn_x",
      windows: {
        a: win("a", DEEP_RESEARCH_WINDOW_KIND, "spn_y"),
      },
    };
    expect(collectDeepResearchSpawnIds(source)).toEqual(
      collectDeepResearchSpawnIds(source),
    );
  });

  it("includes recent spawn ids after closed windows (ob)", () => {
    const ids = collectDeepResearchSpawnIds({
      currentSpawnId: "spn_current",
      windows: {
        w1: win("w1", DEEP_RESEARCH_WINDOW_KIND, "spn_open"),
      },
      recentSpawnIds: ["spn_open", "spn_chased_closed", "  "],
    });
    expect(ids).toEqual([
      "spn_current",
      "spn_open",
      "spn_chased_closed",
    ]);
  });
});
