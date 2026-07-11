import { describe, expect, it } from "vitest";
import {
  composeWriteModeTwinCollectiveAnalysis,
  formatWriteModeTwinCollectiveAnalysisSummary,
} from "./writeModeTwinCollectiveAnalysisCompose";

const twin_slices = [
  {
    parent_asset_id: "asset-1",
    insights: ["scaling claim holds in compute-optimal regimes"],
    questions: ["Where does it break?"],
  },
  {
    parent_asset_id: "asset-2",
    insights: ["attention efficiency tradeoffs"],
    questions: [],
  },
];

const chase_slots = [
  {
    slot_id: "s1",
    question_id: "q1",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    findings: ["finding A from chase"],
    body: "What evidence supports scaling?",
  },
  {
    slot_id: "s2",
    question_id: "q2",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    findings: ["finding B from chase"],
    body: "Counter-evidence?",
  },
];

describe("composeWriteModeTwinCollectiveAnalysis", () => {
  it("twin draft + draft analysis ready", () => {
    const c = composeWriteModeTwinCollectiveAnalysis({
      session_id: "sess-1",
      draft_id: "draft-1",
      parent_asset_id: "asset-1",
      twin_slices,
      base_draft_html: "<p>Opening paragraph</p>",
      chase_slots,
      analysis_kind: "draft_analysis",
      operator_ack: true,
    });
    expect(c.twin_draft.draft_ready).toBe(true);
    expect(c.collective_analysis.analysis_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.authority).toBe(
      "write_mode_twin_collective_analysis_compose_advisory",
    );
    expect(formatWriteModeTwinCollectiveAnalysisSummary(c)).toMatch(
      /analysis_written=false/,
    );
  });

  it("full analysis ready when all completed + ack", () => {
    const c = composeWriteModeTwinCollectiveAnalysis({
      session_id: "sess-2",
      draft_id: "draft-2",
      parent_asset_id: "asset-1",
      twin_slices,
      chase_slots,
      analysis_kind: "full_analysis",
      operator_ack: true,
    });
    expect(c.collective_analysis.analysis.kind).toBe("full_analysis");
    expect(c.pack_ready).toBe(true);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("operator_ack false blocks pack", () => {
    const c = composeWriteModeTwinCollectiveAnalysis({
      session_id: "sess-3",
      draft_id: "d",
      parent_asset_id: "asset-1",
      twin_slices,
      chase_slots,
      analysis_kind: "draft_analysis",
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("require_both false allows either path", () => {
    const c = composeWriteModeTwinCollectiveAnalysis({
      session_id: "sess-4",
      draft_id: "d",
      parent_asset_id: "asset-1",
      twin_slices: [
        {
          parent_asset_id: "asset-1",
          insights: ["only one insight"],
          questions: [],
        },
      ],
      chase_slots,
      analysis_kind: "draft_analysis",
      operator_ack: true,
      require_both: false,
    });
    // twin draft may be ready with one slice; analysis ready with 2 slots
    expect(c.collective_analysis.analysis_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });
});
