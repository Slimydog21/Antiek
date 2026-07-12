import { describe, expect, it } from "vitest";
import {
  composeCompetitionDrQualityWrite,
  formatCompetitionDrQualityWriteSummary,
} from "./competitionDrQualityWriteCompose";

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

describe("composeCompetitionDrQualityWrite", () => {
  it("quality source + write ready", () => {
    const c = composeCompetitionDrQualityWrite({
      session_id: "sess-1",
      draft_id: "draft-1",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      quality_floor: 0.5,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.quality_source.pack_ready).toBe(true);
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.authority).toBe("competition_dr_quality_write_compose_advisory");
    expect(formatCompetitionDrQualityWriteSummary(c)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });

  it("budget would_exceed blocks quality pack", () => {
    const c = composeCompetitionDrQualityWrite({
      session_id: "sess-2",
      draft_id: "draft-2",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.9,
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.quality_source.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeCompetitionDrQualityWrite({
      session_id: "sess-3",
      draft_id: "draft-3",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
  });

  it("caller twin_slices override", () => {
    const c = composeCompetitionDrQualityWrite({
      session_id: "sess-4",
      draft_id: "draft-4",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: true,
      twin_slices: [
        {
          parent_asset_id: "asset-1",
          insights: ["A", "B"],
          questions: ["Q?"],
        },
      ],
      chase_slots: [
        {
          slot_id: "s1",
          question_id: "q1",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f1"],
        },
        {
          slot_id: "s2",
          question_id: "q2",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f2"],
        },
      ],
      analysis_kind: "full_analysis",
    });
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });
});
