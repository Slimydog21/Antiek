import { describe, expect, it } from "vitest";
import {
  composeTwinSubstrateCrossAssetMerge,
  formatTwinSubstrateCrossAssetMergeSummary,
} from "./twinSubstrateCrossAssetMergeCompose";

describe("composeTwinSubstrateCrossAssetMerge", () => {
  it("merges substrate intent without writing or executing", () => {
    const c = composeTwinSubstrateCrossAssetMerge({
      pack_id: "pack-1",
      operator_ack: true,
      slices: [
        {
          parent_asset_id: "a1",
          twin_asset_id: "t1",
          insights: ["claim holds under noise"],
          questions: ["what is the sample size?"],
        },
        {
          parent_asset_id: "a2",
          insights: ["routing cost is non-linear"],
          questions: [],
        },
      ],
    });
    expect(c.merge_ready).toBe(true);
    expect(c.parent_count).toBe(2);
    expect(c.insight_count).toBe(2);
    expect(c.question_count).toBe(1);
    expect(c.merge_executed).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "twin_substrate_cross_asset_merge_compose_advisory",
    );
    expect(formatTwinSubstrateCrossAssetMergeSummary(c)).toMatch(
      /merge_executed=false/,
    );
  });

  it("not ready without ack or empty substrate", () => {
    const noAck = composeTwinSubstrateCrossAssetMerge({
      pack_id: "p",
      operator_ack: false,
      slices: [
        { parent_asset_id: "a", insights: ["x"], questions: [] },
        { parent_asset_id: "b", insights: [], questions: ["y"] },
      ],
    });
    expect(noAck.merge_ready).toBe(false);
    expect(noAck.merge_executed).toBe(false);

    const empty = composeTwinSubstrateCrossAssetMerge({
      pack_id: "p",
      operator_ack: true,
      slices: [
        { parent_asset_id: "a", insights: [], questions: [] },
        { parent_asset_id: "b", insights: [], questions: [] },
      ],
    });
    expect(empty.merge_ready).toBe(false);
  });

  it("rejects <2 slices and duplicate parents", () => {
    expect(() =>
      composeTwinSubstrateCrossAssetMerge({
        pack_id: "p",
        operator_ack: true,
        slices: [{ parent_asset_id: "a", insights: ["x"], questions: [] }],
      }),
    ).toThrow(/at least 2/);
    expect(() =>
      composeTwinSubstrateCrossAssetMerge({
        pack_id: "p",
        operator_ack: true,
        slices: [
          { parent_asset_id: "a", insights: ["x"], questions: [] },
          { parent_asset_id: "a", insights: ["y"], questions: [] },
        ],
      }),
    ).toThrow(/duplicate/);
  });
});
