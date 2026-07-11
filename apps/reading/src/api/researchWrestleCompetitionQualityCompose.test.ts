import { describe, expect, it } from "vitest";
import {
  composeResearchWrestleCompetitionQuality,
  formatResearchWrestleCompetitionQualitySummary,
} from "./researchWrestleCompetitionQualityCompose";

const DECISIONS = [
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

const CITATIONS = [
  {
    citation_id: "c1",
    family: "arxiv" as const,
    title: "Scaling Laws under Noise",
    external_id: "arxiv:2301.00001",
  },
  {
    citation_id: "c2",
    family: "substack" as const,
    title: "Research notes on evals",
    url: "https://example.substack.com/p/evals",
  },
];

describe("composeResearchWrestleCompetitionQuality", () => {
  it("session ready when wrestle + quality pack ready", () => {
    const c = composeResearchWrestleCompetitionQuality({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      floating_instance_count: 2,
      completed_floating_count: 1,
      twin_insight_count: 3,
      twin_question_count: 2,
      open_question_count: 1,
      preferred_view_mode: "floating",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      quality_floor: 0.5,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.wrestle.wrestle_ready).toBe(true);
    expect(c.competition_quality.pack_ready).toBe(true);
    expect(c.session_ready).toBe(true);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.authority).toBe(
      "research_wrestle_competition_quality_compose_advisory",
    );
    const s = formatResearchWrestleCompetitionQualitySummary(c);
    expect(s).toMatch(/live_dispatch_authorized=false/);
    expect(s).toMatch(/remote_fetched=false/);
    expect(s).toMatch(/backlog_mutated=false/);
  });

  it("require_no_behind blocks session_ready", () => {
    const c = composeResearchWrestleCompetitionQuality({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      floating_instance_count: 2,
      completed_floating_count: 1,
      twin_insight_count: 2,
      twin_question_count: 1,
      open_question_count: 1,
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.9,
      would_exceed: false,
      operator_ack: true,
      require_no_behind_gaps: true,
    });
    expect(c.competition_quality.pack_ready).toBe(false);
    expect(c.session_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("quality below floor blocks", () => {
    const c = composeResearchWrestleCompetitionQuality({
      session_id: "s",
      parent_asset_id: "p",
      floating_instance_count: 1,
      completed_floating_count: 0,
      twin_insight_count: 1,
      twin_question_count: 1,
      open_question_count: 1,
      competitor_decisions: [
        {
          competitor: "X",
          area: "budget_controls",
          decision_summary: "hard caps",
          antiek_status: "ahead",
        },
      ],
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.2,
      quality_floor: 0.5,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.competition_quality.pack_ready).toBe(false);
    expect(c.session_ready).toBe(false);
  });

  it("would_exceed without override blocks", () => {
    const c = composeResearchWrestleCompetitionQuality({
      session_id: "s",
      parent_asset_id: "p",
      floating_instance_count: 2,
      completed_floating_count: 1,
      twin_insight_count: 2,
      twin_question_count: 1,
      open_question_count: 0,
      competitor_decisions: [],
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.9,
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.session_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("ack false blocks quality pack and session", () => {
    const c = composeResearchWrestleCompetitionQuality({
      session_id: "s",
      parent_asset_id: "p",
      floating_instance_count: 2,
      completed_floating_count: 1,
      twin_insight_count: 2,
      twin_question_count: 1,
      open_question_count: 1,
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.competition_quality.pack_ready).toBe(false);
    expect(c.session_ready).toBe(false);
  });
});
