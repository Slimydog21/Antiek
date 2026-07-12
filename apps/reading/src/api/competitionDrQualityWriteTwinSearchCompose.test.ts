import { describe, expect, it } from "vitest";
import {
  composeCompetitionDrQualityWriteTwinSearch,
  formatCompetitionDrQualityWriteTwinSearchSummary,
} from "./competitionDrQualityWriteTwinSearchCompose";

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

describe("composeCompetitionDrQualityWriteTwinSearch", () => {
  it("quality write + twin search ready on competition terms", () => {
    const c = composeCompetitionDrQualityWriteTwinSearch({
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
      search_query: "scaling orchestration citations",
    });
    expect(c.quality_write.pack_ready).toBe(true);
    expect(c.twin_search.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_corpus.length).toBeGreaterThanOrEqual(2);
    expect(c.twin_search.search.hits.length).toBeGreaterThan(0);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.remote_index_queried).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.authority).toBe(
      "competition_dr_quality_write_twin_search_compose_advisory",
    );
    expect(formatCompetitionDrQualityWriteTwinSearchSummary(c)).toMatch(
      /remote_index_queried=false/,
    );
  });

  it("budget would_exceed blocks quality write and pack", () => {
    const c = composeCompetitionDrQualityWriteTwinSearch({
      session_id: "sess-2",
      draft_id: "draft-2",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv"],
      citations: [CITATIONS[0]],
      quality_overall: 0.9,
      would_exceed: true,
      operator_ack: true,
      search_query: "scaling",
    });
    expect(c.quality_write.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeCompetitionDrQualityWriteTwinSearch({
      session_id: "sess-3",
      draft_id: "draft-3",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: false,
      search_query: "scaling",
    });
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("extra twin records expand corpus and stay pure", () => {
    const c = composeCompetitionDrQualityWriteTwinSearch({
      session_id: "sess-4",
      draft_id: "draft-4",
      parent_asset_id: "asset-1",
      competitor_decisions: DECISIONS,
      requested_families: ["arxiv", "substack"],
      citations: CITATIONS,
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: true,
      search_query: "evals graph",
      extra_twin_records: [
        {
          twin_id: "twin-extra-1",
          parent_asset_id: "asset-extra",
          insights: ["Knowledge graph evals"],
          questions: ["How to score graph coverage?"],
          source_label: "extra",
        },
      ],
    });
    expect(c.twin_corpus.some((r) => r.twin_id === "twin-extra-1")).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
    expect(c.remote_index_queried).toBe(false);
  });
});
