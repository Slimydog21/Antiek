import { describe, expect, it } from "vitest";
import {
  composeResearchWorkstationInterrogationLoop,
  formatResearchWorkstationInterrogationLoopSummary,
} from "./researchWorkstationInterrogationLoopCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];

const questions = [
  {
    question_id: "q1",
    body: "What evidence supports the scaling claim?",
    priority: 2,
  },
  {
    question_id: "q2",
    body: "Where do scaling laws break?",
    priority: 1,
  },
];

describe("composeResearchWorkstationInterrogationLoop", () => {
  it("chase + prompt pack ready under budget", () => {
    const c = composeResearchWorkstationInterrogationLoop({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      questions,
      chase_mode: "swarm_fanout",
      prior_records: [
        {
          record_id: "i1",
          kind: "insight",
          body: "Prior note: compute-optimal regimes matter",
        },
      ],
      user_prompt: "Interrogate the paper and chase open questions",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 25,
      spent_usd: 3,
      projected_cost_usd_high: 0.4,
      would_exceed: false,
      source_families: ["arxiv", "substack"],
      operator_ack: true,
    });
    expect(c.chase.chase_ready).toBe(true);
    expect(c.chase.slot_count).toBe(2);
    expect(c.prompt_pack.pack_ready).toBe(true);
    expect(c.loop_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.authority).toBe(
      "research_workstation_interrogation_loop_compose_advisory",
    );
    expect(formatResearchWorkstationInterrogationLoopSummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("budget would_exceed blocks chase_ready and loop", () => {
    const c = composeResearchWorkstationInterrogationLoop({
      session_id: "sess-2",
      parent_asset_id: "a",
      questions: [questions[0]],
      chase_mode: "single_question",
      user_prompt: "Chase",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.chase.budget_ready).toBe(false);
    expect(c.chase.chase_ready).toBe(false);
    expect(c.loop_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("operator_ack false blocks loop", () => {
    const c = composeResearchWorkstationInterrogationLoop({
      session_id: "sess-3",
      parent_asset_id: "a",
      questions,
      chase_mode: "swarm_fanout",
      user_prompt: "Go",
      selected_model_id: "grok-4.5",
      models,
      daily_cap_usd: 10,
      spent_usd: 1,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.loop_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.record_persisted).toBe(false);
  });

  it("collective_merge_after mode still pure", () => {
    const c = composeResearchWorkstationInterrogationLoop({
      session_id: "sess-4",
      parent_asset_id: "a",
      questions,
      chase_mode: "collective_merge_after",
      user_prompt: "Merge chases after completion",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 20,
      spent_usd: 2,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.chase.chase_mode).toBe("collective_merge_after");
    expect(c.pack_dispatched).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });
});
