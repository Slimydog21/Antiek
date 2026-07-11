import { describe, expect, it } from "vitest";
import {
  composeChaseCompletionCollectiveAnalysis,
  formatChaseCompletionCollectiveAnalysisSummary,
} from "./chaseCompletionCollectiveAnalysisCompose";

const SLOTS = [
  {
    slot_id: "chase_1_q1",
    question_id: "q1",
    parent_asset_id: "paper-1",
    status: "completed" as const,
    findings: ["claim A supported by arxiv:123"],
  },
  {
    slot_id: "chase_2_q2",
    question_id: "q2",
    parent_asset_id: "paper-1",
    status: "completed" as const,
    findings: ["gap: missing ablation"],
  },
];

describe("composeChaseCompletionCollectiveAnalysis", () => {
  it("draft analysis ready without write", () => {
    const c = composeChaseCompletionCollectiveAnalysis({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      slots: SLOTS,
      kind: "draft_analysis",
      operator_ack: false,
    });
    expect(c.analysis_ready).toBe(true);
    expect(c.analysis.kind).toBe("draft_analysis");
    expect(c.analysis_written).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.analysis.findings.length).toBe(2);
    expect(c.authority).toBe(
      "chase_completion_collective_analysis_compose_advisory",
    );
    const s = formatChaseCompletionCollectiveAnalysisSummary(c);
    expect(s).toMatch(/analysis_written=false/);
    expect(s).toMatch(/live_dispatched=false/);
    expect(s).toMatch(/pack_dispatched=false/);
  });

  it("full analysis ready when all completed + ack", () => {
    const c = composeChaseCompletionCollectiveAnalysis({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      slots: SLOTS,
      kind: "full_analysis",
      operator_ack: true,
    });
    expect(c.analysis_ready).toBe(true);
    expect(c.completed_slot_count).toBe(2);
    expect(c.analysis_written).toBe(false);
  });

  it("throws on full_analysis with open slot", () => {
    expect(() =>
      composeChaseCompletionCollectiveAnalysis({
        session_id: "sess-1",
        parent_asset_id: "paper-1",
        slots: [
          SLOTS[0],
          {
            slot_id: "chase_2_q2",
            question_id: "q2",
            parent_asset_id: "paper-1",
            status: "open",
          },
        ],
        kind: "full_analysis",
        operator_ack: true,
      }),
    ).toThrow(/completed/);
  });

  it("rejects fewer than 2 slots", () => {
    expect(() =>
      composeChaseCompletionCollectiveAnalysis({
        session_id: "s",
        parent_asset_id: "p",
        slots: [SLOTS[0]],
        kind: "draft_analysis",
        operator_ack: false,
      }),
    ).toThrow(/at least 2/);
  });

  it("rejects cross-parent slots", () => {
    expect(() =>
      composeChaseCompletionCollectiveAnalysis({
        session_id: "s",
        parent_asset_id: "paper-1",
        slots: [
          SLOTS[0],
          {
            slot_id: "x",
            question_id: "q2",
            parent_asset_id: "other",
            status: "completed",
          },
        ],
        kind: "draft_analysis",
        operator_ack: false,
      }),
    ).toThrow(/parent_asset_id/);
  });

  it("skips closed slots", () => {
    const c = composeChaseCompletionCollectiveAnalysis({
      session_id: "s",
      parent_asset_id: "paper-1",
      slots: [
        SLOTS[0],
        SLOTS[1],
        {
          slot_id: "closed-1",
          question_id: "q3",
          parent_asset_id: "paper-1",
          status: "closed",
        },
      ],
      kind: "draft_analysis",
      operator_ack: false,
    });
    expect(c.selected_slot_ids).not.toContain("closed-1");
    expect(c.selected_slot_ids.length).toBe(2);
  });
});
