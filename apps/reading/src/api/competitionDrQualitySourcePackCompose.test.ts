import { describe, expect, it } from "vitest";
import {
  composeCompetitionDrQualitySourcePack,
  formatCompetitionDrQualitySourcePackSummary,
} from "./competitionDrQualitySourcePackCompose";

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

describe("composeCompetitionDrQualitySourcePack", () => {
  it("pack ready with quality, citations, competition advisory", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "sess-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      quality_floor: 0.5,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.pack_ready).toBe(true);
    expect(c.citations.pack_ready).toBe(true);
    expect(c.quality_budget.gate_ready).toBe(true);
    expect(c.competition.behind_count).toBe(1);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.authority).toBe(
      "competition_dr_quality_source_pack_compose_advisory",
    );
    const s = formatCompetitionDrQualitySourcePackSummary(c);
    expect(s).toMatch(/live_dispatch_authorized=false/);
    expect(s).toMatch(/remote_fetched=false/);
    expect(s).toMatch(/backlog_mutated=false/);
  });

  it("require_no_behind_gaps blocks when behind", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "sess-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.9,
      would_exceed: false,
      operator_ack: true,
      require_no_behind_gaps: true,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("quality below floor blocks", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "s",
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
    expect(c.quality_budget.quality_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
  });

  it("would_exceed blocks without override", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "s",
      competitor_decisions: [],
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.9,
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.quality_budget.budget_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("empty citations not pack ready", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "s",
      competitor_decisions: [],
      requested_families: ["arxiv"],
      citations: [],
      quality_overall: 0.9,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.citations.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
  });

  it("ack false not ready", () => {
    const c = composeCompetitionDrQualitySourcePack({
      session_id: "s",
      competitor_decisions: [],
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.9,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
  });
});
