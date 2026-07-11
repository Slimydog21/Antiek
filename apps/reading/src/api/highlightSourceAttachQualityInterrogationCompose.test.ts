import { describe, expect, it } from "vitest";
import {
  composeHighlightSourceAttachQualityInterrogation,
  formatHighlightSourceAttachQualityInterrogationSummary,
} from "./highlightSourceAttachQualityInterrogationCompose";

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
    body: "How does this highlight relate to scaling laws?",
    priority: 2,
  },
  {
    question_id: "q2",
    body: "What counter-evidence exists?",
    priority: 1,
  },
];

describe("composeHighlightSourceAttachQualityInterrogation", () => {
  it("highlight launch + source interrogation ready", () => {
    const c = composeHighlightSourceAttachQualityInterrogation({
      parent_asset_id: "book-1",
      highlight: "power-law scaling of loss with compute",
      gated: false,
      preferred_view_mode: "floating",
      would_exceed: false,
      selected_model_id: "gpt-5.5",
      operator_ack: true,
      session_id: "sess-1",
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.88,
      quality_floor: 0.7,
      questions,
      chase_mode: "swarm_fanout",
      models,
      daily_cap_usd: 30,
      spent_usd: 4,
      projected_cost_usd_high: 0.4,
    });
    expect(c.highlight_launch.launch_ready).toBe(true);
    expect(c.source_interrogation.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.authority).toBe(
      "highlight_source_attach_quality_interrogation_compose_advisory",
    );
    expect(formatHighlightSourceAttachQualityInterrogationSummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("gated highlight fails closed", () => {
    expect(() =>
      composeHighlightSourceAttachQualityInterrogation({
        parent_asset_id: "book-1",
        highlight: "secret gated passage",
        gated: true,
        would_exceed: false,
        operator_ack: true,
        session_id: "sess-1",
        requested_families: ["arxiv"],
        sources: [sources[0]],
        quality_overall: 0.9,
        questions: [questions[0]],
        chase_mode: "single_question",
        models,
        daily_cap_usd: 20,
        spent_usd: 1,
      }),
    ).toThrow(/gated/i);
  });

  it("budget would_exceed blocks", () => {
    const c = composeHighlightSourceAttachQualityInterrogation({
      parent_asset_id: "book-1",
      highlight: "claim",
      gated: false,
      would_exceed: true,
      operator_ack: true,
      session_id: "sess-1",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      questions: [questions[0]],
      chase_mode: "single_question",
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeHighlightSourceAttachQualityInterrogation({
      parent_asset_id: "book-1",
      highlight: "claim",
      gated: false,
      would_exceed: false,
      operator_ack: false,
      session_id: "sess-1",
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.9,
      questions,
      chase_mode: "swarm_fanout",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });
});
