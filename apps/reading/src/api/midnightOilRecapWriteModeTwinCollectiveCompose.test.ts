import { describe, expect, it } from "vitest";
import {
  composeMidnightOilRecapWriteModeTwinCollective,
  formatMidnightOilRecapWriteModeTwinCollectiveSummary,
} from "./midnightOilRecapWriteModeTwinCollectiveCompose";

const goals = [
  {
    goal_id: "g1",
    title: "Survey arxiv scaling laws",
    status: "done" as const,
    notes: "Found key papers",
  },
  {
    goal_id: "g2",
    title: "Synthesize substack claims",
    status: "done" as const,
    notes: "Draft synthesis",
  },
  {
    goal_id: "g3",
    title: "Open counter-claims",
    status: "pending" as const,
  },
];

describe("composeMidnightOilRecapWriteModeTwinCollective", () => {
  it("recap + write pack ready", () => {
    const c = composeMidnightOilRecapWriteModeTwinCollective({
      run_id: "run-1",
      operator_id: "op-1",
      work_minutes_planned: 120,
      work_minutes_actual: 115,
      goals,
      price_ceiling_usd: 40,
      spend_usd: 28,
      artifact_ids: ["art-1"],
      operator_ack: true,
      session_id: "sess-1",
      draft_id: "draft-1",
      parent_asset_id: "asset-1",
    });
    expect(c.recap.recap_ready).toBe(true);
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(formatMidnightOilRecapWriteModeTwinCollectiveSummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("blocks without operator_ack", () => {
    const c = composeMidnightOilRecapWriteModeTwinCollective({
      run_id: "run-2",
      operator_id: "op-1",
      work_minutes_planned: 60,
      work_minutes_actual: 50,
      goals,
      price_ceiling_usd: 20,
      spend_usd: 10,
      operator_ack: false,
      session_id: "s",
      draft_id: "d",
      parent_asset_id: "a",
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("blocks when no progress on recap", () => {
    const c = composeMidnightOilRecapWriteModeTwinCollective({
      run_id: "run-3",
      operator_id: "op-1",
      work_minutes_planned: 60,
      work_minutes_actual: 0,
      goals: [{ goal_id: "g1", title: "T", status: "pending" }],
      price_ceiling_usd: 20,
      spend_usd: 0,
      operator_ack: true,
      session_id: "s",
      draft_id: "d",
      parent_asset_id: "a",
    });
    expect(c.recap.recap_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
  });

  it("caller twin_slices override", () => {
    const c = composeMidnightOilRecapWriteModeTwinCollective({
      run_id: "run-4",
      operator_id: "op-1",
      work_minutes_planned: 90,
      work_minutes_actual: 80,
      goals,
      price_ceiling_usd: 30,
      spend_usd: 20,
      operator_ack: true,
      session_id: "s",
      draft_id: "d",
      parent_asset_id: "a",
      twin_slices: [
        {
          parent_asset_id: "a",
          insights: ["Caller insight A", "Caller insight B"],
          questions: ["Q1?"],
        },
      ],
      chase_slots: [
        {
          slot_id: "s1",
          question_id: "q1",
          parent_asset_id: "a",
          status: "completed",
          findings: ["f1"],
        },
        {
          slot_id: "s2",
          question_id: "q2",
          parent_asset_id: "a",
          status: "completed",
          findings: ["f2"],
        },
      ],
      analysis_kind: "full_analysis",
    });
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.analysis_written).toBe(false);
  });
});
