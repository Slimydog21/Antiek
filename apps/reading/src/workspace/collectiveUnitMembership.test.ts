import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearCollectiveUnitMembership,
  COLLECTIVE_UNIT_MEMBERSHIP_KEY,
  COLLECTIVE_UNIT_MEMBERSHIP_MAX,
  getCollectiveUnitMembership,
  getLastCollectiveUnitMembership,
  restoreCollectiveSelection,
  storeCollectiveUnitMembership,
} from "./collectiveUnitMembership";

describe("collectiveUnitMembership (py)", () => {
  beforeEach(() => {
    clearCollectiveUnitMembership();
  });
  afterEach(() => {
    clearCollectiveUnitMembership();
  });

  it("stores and retrieves membership by collective_id", () => {
    const m = storeCollectiveUnitMembership({
      collective_id: "col_1",
      spawn_ids: ["spn_a", "spn_b", "spn_a"],
      parent_asset_id: "paper",
      document_id: "doc_analysis",
    });
    expect(m).toEqual(
      expect.objectContaining({
        collective_id: "col_1",
        spawn_ids: ["spn_a", "spn_b"],
        parent_asset_id: "paper",
        document_id: "doc_analysis",
      }),
    );
    expect(getCollectiveUnitMembership("col_1")?.spawn_ids).toEqual([
      "spn_a",
      "spn_b",
    ]);
    expect(getLastCollectiveUnitMembership()?.collective_id).toBe("col_1");
    const raw = window.sessionStorage.getItem(COLLECTIVE_UNIT_MEMBERSHIP_KEY);
    expect(raw).toMatch(/col_1/);
  });

  it("ignores empty collective_id and empty spawn_ids", () => {
    expect(
      storeCollectiveUnitMembership({
        collective_id: "  ",
        spawn_ids: ["x"],
      }),
    ).toBeNull();
    expect(
      storeCollectiveUnitMembership({
        collective_id: "col_x",
        spawn_ids: ["", "  "],
      }),
    ).toBeNull();
    expect(getLastCollectiveUnitMembership()).toBeNull();
  });

  it("restoreCollectiveSelection intersects available preserving order", () => {
    const m = storeCollectiveUnitMembership({
      collective_id: "col_r",
      spawn_ids: ["a", "b", "c"],
    });
    expect(restoreCollectiveSelection(m, ["c", "a", "z"])).toEqual(["a", "c"]);
    expect(restoreCollectiveSelection(m, [])).toEqual([]);
    expect(restoreCollectiveSelection(null, ["a"])).toEqual([]);
  });

  it("caps stored units at MAX", () => {
    for (let i = 0; i < COLLECTIVE_UNIT_MEMBERSHIP_MAX + 5; i++) {
      storeCollectiveUnitMembership({
        collective_id: `col_${i}`,
        spawn_ids: [`spn_${i}`],
      });
    }
    // Oldest should be gone; newest kept.
    expect(getCollectiveUnitMembership("col_0")).toBeNull();
    expect(
      getCollectiveUnitMembership(
        `col_${COLLECTIVE_UNIT_MEMBERSHIP_MAX + 4}`,
      ),
    ).not.toBeNull();
    expect(getLastCollectiveUnitMembership()?.collective_id).toBe(
      `col_${COLLECTIVE_UNIT_MEMBERSHIP_MAX + 4}`,
    );
  });
});
