import { describe, expect, it } from "vitest";
import {
  composeSourceAttachQualityInterrogationTwin,
  formatSourceAttachQualityInterrogationTwinSummary,
} from "./sourceAttachQualityInterrogationTwinCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];

const sources = [
  {
    source_id: "arx-1",
    family: "arxiv" as const,
    title: "Scaling Laws for Neural Language Models",
    external_id: "arxiv:2001.08361",
    html_fragment: "<article>abstract…</article>",
  },
  {
    source_id: "sub-1",
    family: "substack" as const,
    title: "Deep research essay",
    html_fragment: "<article>essay…</article>",
  },
];

const questions = [
  {
    question_id: "q1",
    body: "How do these sources ground multi-hop claims?",
    priority: 2,
  },
  {
    question_id: "q2",
    body: "Where do they disagree with Antiek doctrine?",
    priority: 1,
  },
];

describe("composeSourceAttachQualityInterrogationTwin", () => {
  it("source + twin feed ready", () => {
    const c = composeSourceAttachQualityInterrogationTwin({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.88,
      quality_floor: 0.7,
      would_exceed: false,
      questions,
      chase_mode: "swarm_fanout",
      user_prompt: "Chase with arxiv/substack attached",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 30,
      spent_usd: 4,
      projected_cost_usd_high: 0.4,
      operator_ack: true,
    });
    expect(c.source_interrogation.pack_ready).toBe(true);
    expect(c.twin_feed.feed_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_feed.finding_count).toBe(4); // 2 sources + 2 questions
    expect(c.remote_fetched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "source_attach_quality_interrogation_twin_compose_advisory",
    );
    expect(formatSourceAttachQualityInterrogationTwinSummary(c)).toMatch(
      /twin_written=false/,
    );
  });

  it("budget would_exceed blocks pack_ready", () => {
    const c = composeSourceAttachQualityInterrogationTwin({
      session_id: "sess-2",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [sources[0]],
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
    expect(c.source_interrogation.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeSourceAttachQualityInterrogationTwin({
      session_id: "sess-3",
      parent_asset_id: "a",
      requested_families: ["arxiv", "substack"],
      sources,
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
    expect(c.pack_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("caller twin_findings override derived", () => {
    const c = composeSourceAttachQualityInterrogationTwin({
      session_id: "sess-4",
      parent_asset_id: "asset-1",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      would_exceed: false,
      questions: [questions[0]],
      chase_mode: "single_question",
      user_prompt: "Chase",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
      operator_ack: true,
      twin_findings: [
        {
          source_id: "custom-1",
          body: "Caller insight from completed chase",
          kind: "insight",
        },
      ],
      analysis_excerpt: "Provisional analysis",
    });
    expect(c.twin_feed.finding_count).toBe(1);
    expect(c.twin_feed.insight_count).toBe(1);
    expect(c.pack_ready).toBe(true);
    expect(c.remote_fetched).toBe(false);
  });
});
