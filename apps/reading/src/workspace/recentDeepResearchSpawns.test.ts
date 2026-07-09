import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearRecentDeepResearchSpawnIds,
  listRecentDeepResearchSpawnIds,
  pushRecentDeepResearchSpawnId,
  RECENT_DEEP_RESEARCH_SPAWNS_KEY,
  RECENT_DEEP_RESEARCH_SPAWNS_MAX,
} from "./recentDeepResearchSpawns";

describe("recentDeepResearchSpawns residual (ob)", () => {
  beforeEach(() => {
    clearRecentDeepResearchSpawnIds();
  });
  afterEach(() => {
    clearRecentDeepResearchSpawnIds();
  });

  it("pushes newest first and dedupes", () => {
    pushRecentDeepResearchSpawnId("spn_a");
    pushRecentDeepResearchSpawnId("spn_b");
    pushRecentDeepResearchSpawnId("spn_a");
    expect(listRecentDeepResearchSpawnIds()).toEqual(["spn_a", "spn_b"]);
  });

  it("ignores empty ids (never invent)", () => {
    pushRecentDeepResearchSpawnId("  ");
    pushRecentDeepResearchSpawnId("");
    expect(listRecentDeepResearchSpawnIds()).toEqual([]);
  });

  it("caps ring length", () => {
    for (let i = 0; i < RECENT_DEEP_RESEARCH_SPAWNS_MAX + 5; i++) {
      pushRecentDeepResearchSpawnId(`spn_${i}`);
    }
    const list = listRecentDeepResearchSpawnIds();
    expect(list).toHaveLength(RECENT_DEEP_RESEARCH_SPAWNS_MAX);
    expect(list[0]).toBe(`spn_${RECENT_DEEP_RESEARCH_SPAWNS_MAX + 4}`);
  });

  it("persists via sessionStorage key", () => {
    pushRecentDeepResearchSpawnId("spn_persist");
    const raw = window.sessionStorage.getItem(RECENT_DEEP_RESEARCH_SPAWNS_KEY);
    expect(raw).toMatch(/spn_persist/);
  });
});
