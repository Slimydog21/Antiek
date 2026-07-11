import { describe, expect, it } from "vitest";
import {
  composeWriteModeTwinDraftMerge,
  formatWriteModeTwinDraftMergeSummary,
} from "./writeModeTwinDraftMergeCompose";

describe("composeWriteModeTwinDraftMerge", () => {
  it("builds provisional draft without writing", () => {
    const c = composeWriteModeTwinDraftMerge({
      draft_id: "draft-1",
      base_draft_html: "<p>Opening argument</p>",
      operator_ack: true,
      slices: [
        {
          parent_asset_id: "a1",
          insights: ["claim holds under noise"],
          questions: ["sample size?"],
        },
        {
          parent_asset_id: "a2",
          insights: ["routing is non-linear"],
          questions: [],
        },
      ],
    });
    expect(c.draft_ready).toBe(true);
    expect(c.section_count).toBeGreaterThanOrEqual(4);
    expect(c.draft_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe("write_mode_twin_draft_merge_compose_advisory");
    expect(formatWriteModeTwinDraftMergeSummary(c)).toMatch(
      /draft_written=false/,
    );
  });

  it("not ready without ack or twin content", () => {
    const noAck = composeWriteModeTwinDraftMerge({
      draft_id: "d",
      operator_ack: false,
      slices: [
        {
          parent_asset_id: "a",
          insights: ["x"],
          questions: [],
        },
      ],
    });
    expect(noAck.draft_ready).toBe(false);
    expect(noAck.draft_written).toBe(false);

    const empty = composeWriteModeTwinDraftMerge({
      draft_id: "d",
      operator_ack: true,
      slices: [{ parent_asset_id: "a", insights: [], questions: [] }],
    });
    expect(empty.draft_ready).toBe(false);
  });

  it("rejects empty slices and duplicates", () => {
    expect(() =>
      composeWriteModeTwinDraftMerge({
        draft_id: "d",
        operator_ack: true,
        slices: [],
      }),
    ).toThrow(/slices/);
    expect(() =>
      composeWriteModeTwinDraftMerge({
        draft_id: "d",
        operator_ack: true,
        slices: [
          { parent_asset_id: "a", insights: ["x"], questions: [] },
          { parent_asset_id: "a", insights: ["y"], questions: [] },
        ],
      }),
    ).toThrow(/duplicate/);
  });
});
