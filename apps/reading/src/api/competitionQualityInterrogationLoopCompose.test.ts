import { describe, expect, it } from "vitest";
import {
  composeCompetitionQualityInterrogationLoop,
  formatCompetitionQualityInterrogationLoopSummary,
} from "./competitionQualityInterrogationLoopCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];

const questions = [
  {
    question_id: "q1",
    body: "How do competitors structure multi-hop citations?",
    priority: 2,
  },
  {
    question_id: "q2",
    body: "Where is Antiek ahead on HTML-native research?",
    priority: 1,
  },
];

const competitor_decisions = [
  {
    competitor: "Perplexity",
    area: "citation_grounding" as const,
    decision_summary: "Inline citations with source cards",
    antiek_status: "parity" as const,
  },
  {
    competitor: "OpenAI DR",
    area: "multi_agent_orchestration" as const,
    decision_summary: "Planner + browser agents",
    antiek_status: "behind" as const,
    residual: "strengthen collective floating cohesive pack",
  },
];

const citations = [
  {
    citation_id: "c1",
    family: "arxiv" as const,
    title: "Scaling Laws for Neural Language Models",
    external_id: "arxiv:2001.08361",
  },
  {
    citation_id: "c2",
    family: "substack" as const,
    title: "Deep research essay",
  },
];

describe("composeCompetitionQualityInterrogationLoop", () => {
  it("quality pack + interrogation loop ready", () => {
    const c = composeCompetitionQualityInterrogationLoop({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      competitor_decisions,
      requested_families: ["arxiv", "substack"],
      citations,
      quality_overall: 0.85,
      quality_floor: 0.7,
      would_exceed: false,
      questions,
      chase_mode: "swarm_fanout",
      prior_records: [
        {
          record_id: "i1",
          kind: "insight",
          body: "HTML-native doctrine is a differentiator",
        },
      ],
      user_prompt: "Chase competitor gaps with arxiv/substack rigor",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 30,
      spent_usd: 4,
      projected_cost_usd_high: 0.4,
      source_families: ["arxiv", "substack"],
      operator_ack: true,
    });
    expect(c.quality_pack.pack_ready).toBe(true);
    expect(c.interrogation.loop_ready).toBe(true);
    expect(c.session_ready).toBe(true);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.authority).toBe(
      "competition_quality_interrogation_loop_compose_advisory",
    );
    expect(formatCompetitionQualityInterrogationLoopSummary(c)).toMatch(
      /remote_fetched=false/,
    );
  });

  it("budget would_exceed blocks session_ready", () => {
    const c = composeCompetitionQualityInterrogationLoop({
      session_id: "sess-2",
      parent_asset_id: "a",
      competitor_decisions,
      requested_families: ["arxiv"],
      citations: [citations[0]],
      quality_overall: 0.9,
      would_exceed: true,
      questions: [questions[0]],
      chase_mode: "single_question",
      user_prompt: "Chase",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
    });
    expect(c.session_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("low quality blocks quality pack", () => {
    const c = composeCompetitionQualityInterrogationLoop({
      session_id: "sess-3",
      parent_asset_id: "a",
      competitor_decisions,
      requested_families: ["arxiv"],
      citations: [citations[0]],
      quality_overall: 0.2,
      quality_floor: 0.7,
      would_exceed: false,
      questions,
      chase_mode: "swarm_fanout",
      user_prompt: "Go",
      selected_model_id: "grok-4.5",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
      operator_ack: true,
    });
    expect(c.quality_pack.pack_ready).toBe(false);
    expect(c.session_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeCompetitionQualityInterrogationLoop({
      session_id: "sess-4",
      parent_asset_id: "a",
      competitor_decisions,
      requested_families: ["arxiv", "substack"],
      citations,
      quality_overall: 0.9,
      would_exceed: false,
      questions,
      chase_mode: "swarm_fanout",
      user_prompt: "Interrogate",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
      operator_ack: false,
    });
    expect(c.session_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });
});
