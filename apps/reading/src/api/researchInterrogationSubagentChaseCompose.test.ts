import { describe, expect, it } from "vitest";
import {
  composeResearchInterrogationSubagentChase,
  formatResearchInterrogationSubagentChaseSummary,
} from "./researchInterrogationSubagentChaseCompose";

describe("composeResearchInterrogationSubagentChase", () => {
  it("single_question ready without dispatch", () => {
    const c = composeResearchInterrogationSubagentChase({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      questions: [{ question_id: "q1", body: "What is the scaling law?" }],
      chase_mode: "single_question",
      would_exceed: false,
      source_families: ["arxiv"],
      selected_model_id: "gpt-5",
      operator_ack: true,
    });
    expect(c.chase_ready).toBe(true);
    expect(c.slot_count).toBe(1);
    expect(c.planned_slots[0].live_dispatched).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.authority).toBe(
      "research_interrogation_subagent_chase_compose_advisory",
    );
    const s = formatResearchInterrogationSubagentChaseSummary(c);
    expect(s).toMatch(/live_dispatched=false/);
    expect(s).toMatch(/pack_dispatched=false/);
    expect(s).toMatch(/record_persisted=false/);
    expect(s).toMatch(/prompts_injected=false/);
  });

  it("swarm_fanout plans multiple slots by priority", () => {
    const c = composeResearchInterrogationSubagentChase({
      session_id: "sess-2",
      parent_asset_id: "paper-1",
      questions: [
        { question_id: "q-low", body: "minor", priority: 1 },
        { question_id: "q-high", body: "critical gap", priority: 10 },
      ],
      chase_mode: "swarm_fanout",
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.chase_ready).toBe(true);
    expect(c.slot_count).toBe(2);
    expect(c.planned_slots[0].question_id).toBe("q-high");
    expect(c.live_dispatched).toBe(false);
  });

  it("collective_merge_after is intent only", () => {
    const c = composeResearchInterrogationSubagentChase({
      session_id: "sess-3",
      parent_asset_id: "paper-1",
      questions: [
        { question_id: "q1", body: "A?" },
        { question_id: "q2", body: "B?" },
      ],
      chase_mode: "collective_merge_after",
      would_exceed: false,
      mark_for_twin_record: true,
      operator_ack: true,
    });
    expect(c.chase_ready).toBe(true);
    expect(c.pack_dispatched).toBe(false);
    expect(c.mark_for_twin_record).toBe(true);
    expect(c.record_persisted).toBe(false);
  });

  it("would_exceed without override blocks", () => {
    const c = composeResearchInterrogationSubagentChase({
      session_id: "s",
      parent_asset_id: "p",
      questions: [{ question_id: "q1", body: "x" }],
      chase_mode: "single_question",
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.budget_ready).toBe(false);
    expect(c.chase_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("operator_ack false not ready", () => {
    const c = composeResearchInterrogationSubagentChase({
      session_id: "s",
      parent_asset_id: "p",
      questions: [{ question_id: "q1", body: "x" }],
      chase_mode: "single_question",
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.chase_ready).toBe(false);
  });

  it("rejects single_question with many questions", () => {
    expect(() =>
      composeResearchInterrogationSubagentChase({
        session_id: "s",
        parent_asset_id: "p",
        questions: [
          { question_id: "q1", body: "a" },
          { question_id: "q2", body: "b" },
        ],
        chase_mode: "single_question",
        would_exceed: false,
        operator_ack: true,
      }),
    ).toThrow(/exactly 1/);
  });

  it("rejects empty questions", () => {
    expect(() =>
      composeResearchInterrogationSubagentChase({
        session_id: "s",
        parent_asset_id: "p",
        questions: [],
        chase_mode: "swarm_fanout",
        would_exceed: false,
        operator_ack: true,
      }),
    ).toThrow(/non-empty/);
  });

  it("rejects secret-like model id", () => {
    expect(() =>
      composeResearchInterrogationSubagentChase({
        session_id: "s",
        parent_asset_id: "p",
        questions: [{ question_id: "q1", body: "x" }],
        chase_mode: "single_question",
        would_exceed: false,
        selected_model_id: "sk-secret-key",
        operator_ack: true,
      }),
    ).toThrow(/secret/);
  });
});
