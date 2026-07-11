import { describe, expect, it } from "vitest";
import {
  composeChaseTwinAnalysisLoop,
  formatChaseTwinAnalysisLoopSummary,
} from "./chaseTwinAnalysisLoopCompose";

describe("composeChaseTwinAnalysisLoop", () => {
  it("loop ready when chase + twin + draft analysis ready", () => {
    const c = composeChaseTwinAnalysisLoop({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      questions: [
        { question_id: "q1", body: "What is the core claim?", priority: 2 },
        { question_id: "q2", body: "What evidence is missing?", priority: 1 },
      ],
      chase_mode: "swarm_fanout",
      would_exceed: false,
      source_families: ["arxiv"],
      operator_ack: true,
      analysis_kind: "draft_analysis",
      analysis_excerpt: "draft collective scaffold",
      completed_slots: [
        {
          slot_id: "chase_1_q1",
          question_id: "q1",
          parent_asset_id: "paper-1",
          status: "completed",
          findings: ["claim A supported"],
          body: "What is the core claim?",
        },
        {
          slot_id: "chase_2_q2",
          question_id: "q2",
          parent_asset_id: "paper-1",
          status: "completed",
          findings: ["gap: missing ablation"],
          body: "What evidence is missing?",
        },
      ],
      mark_for_prompt_context: true,
    });
    expect(c.chase.chase_ready).toBe(true);
    expect(c.twin_feed?.feed_ready).toBe(true);
    expect(c.analysis?.analysis_ready).toBe(true);
    expect(c.loop_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.authority).toBe("chase_twin_analysis_loop_compose_advisory");
    const s = formatChaseTwinAnalysisLoopSummary(c);
    expect(s).toMatch(/live_dispatched=false/);
    expect(s).toMatch(/twin_written=false/);
    expect(s).toMatch(/analysis_written=false/);
  });

  it("not loop ready with one completed slot", () => {
    const c = composeChaseTwinAnalysisLoop({
      session_id: "s",
      parent_asset_id: "p",
      questions: [{ question_id: "q1", body: "Only one?" }],
      chase_mode: "single_question",
      would_exceed: false,
      operator_ack: true,
      analysis_kind: "draft_analysis",
      completed_slots: [
        {
          slot_id: "only",
          question_id: "q1",
          parent_asset_id: "p",
          status: "completed",
          findings: ["one finding"],
        },
      ],
    });
    expect(c.chase.chase_ready).toBe(true);
    expect(c.analysis).toBeNull();
    expect(c.loop_ready).toBe(false);
  });

  it("budget would_exceed blocks chase and loop", () => {
    const c = composeChaseTwinAnalysisLoop({
      session_id: "s",
      parent_asset_id: "p",
      questions: [
        { question_id: "q1", body: "A?" },
        { question_id: "q2", body: "B?" },
      ],
      chase_mode: "swarm_fanout",
      would_exceed: true,
      operator_ack: true,
      analysis_kind: "draft_analysis",
      completed_slots: [
        {
          slot_id: "a",
          question_id: "q1",
          parent_asset_id: "p",
          status: "completed",
          findings: ["x"],
        },
        {
          slot_id: "b",
          question_id: "q2",
          parent_asset_id: "p",
          status: "completed",
          findings: ["y"],
        },
      ],
    });
    expect(c.chase.chase_ready).toBe(false);
    expect(c.loop_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("ack false not ready", () => {
    const c = composeChaseTwinAnalysisLoop({
      session_id: "s",
      parent_asset_id: "p",
      questions: [
        { question_id: "q1", body: "A?" },
        { question_id: "q2", body: "B?" },
      ],
      chase_mode: "swarm_fanout",
      would_exceed: false,
      operator_ack: false,
      analysis_kind: "draft_analysis",
      completed_slots: [
        {
          slot_id: "a",
          question_id: "q1",
          parent_asset_id: "p",
          status: "completed",
          findings: ["x"],
        },
        {
          slot_id: "b",
          question_id: "q2",
          parent_asset_id: "p",
          status: "completed",
          findings: ["y"],
        },
      ],
    });
    expect(c.loop_ready).toBe(false);
  });
});
