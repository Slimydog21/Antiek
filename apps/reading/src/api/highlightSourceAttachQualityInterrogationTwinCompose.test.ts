import { describe, expect, it } from "vitest";
import {
  composeHighlightSourceAttachQualityInterrogationTwin,
  formatHighlightSourceAttachQualityInterrogationTwinSummary,
} from "./highlightSourceAttachQualityInterrogationTwinCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];
const sources = [
  {
    source_id: "arx-1",
    family: "arxiv" as const,
    title: "Scaling Laws for Neural Language Models",
    html_fragment: "<article>abstract…</article>",
  },
];
const questions = [
  {
    question_id: "q1",
    body: "How does this highlight relate?",
    priority: 2,
  },
];

describe("composeHighlightSourceAttachQualityInterrogationTwin", () => {
  it("highlight pack + twin ready", () => {
    const c = composeHighlightSourceAttachQualityInterrogationTwin({
      parent_asset_id: "book-1",
      highlight: "power-law scaling",
      gated: false,
      would_exceed: false,
      selected_model_id: "gpt-5.5",
      operator_ack: true,
      session_id: "sess-1",
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      questions,
      chase_mode: "single_question",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
    });
    expect(c.highlight_pack.pack_ready).toBe(true);
    expect(c.twin_feed.feed_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    // highlight + 1 source + 1 question
    expect(c.twin_feed.finding_count).toBe(3);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(
      formatHighlightSourceAttachQualityInterrogationTwinSummary(c),
    ).toMatch(/twin_written=false/);
  });

  it("budget blocks", () => {
    const c = composeHighlightSourceAttachQualityInterrogationTwin({
      parent_asset_id: "book-1",
      highlight: "claim",
      gated: false,
      would_exceed: true,
      operator_ack: true,
      session_id: "s",
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      questions,
      chase_mode: "single_question",
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("operator_ack false", () => {
    const c = composeHighlightSourceAttachQualityInterrogationTwin({
      parent_asset_id: "book-1",
      highlight: "claim",
      gated: false,
      would_exceed: false,
      operator_ack: false,
      session_id: "s",
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      questions,
      chase_mode: "single_question",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });

  it("caller twin_findings", () => {
    const c = composeHighlightSourceAttachQualityInterrogationTwin({
      parent_asset_id: "book-1",
      highlight: "claim",
      gated: false,
      would_exceed: false,
      selected_model_id: "gpt-5.5",
      operator_ack: true,
      session_id: "s",
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      questions,
      chase_mode: "single_question",
      models,
      daily_cap_usd: 20,
      spent_usd: 1,
      twin_findings: [
        { source_id: "c1", body: "Caller insight", kind: "insight" },
      ],
    });
    expect(c.twin_feed.finding_count).toBe(1);
    expect(c.pack_ready).toBe(true);
  });
});
