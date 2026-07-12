import { describe, expect, it } from "vitest";
import {
  composeHtmlNativeCompetitionWriteTwinSearch,
  formatHtmlNativeCompetitionWriteTwinSearchSummary,
} from "./htmlNativeCompetitionWriteTwinSearchCompose";

const COMPETITION = {
  draft_id: "draft-1",
  parent_asset_id: "asset-1",
  competitor_decisions: [
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
  ],
  requested_families: ["arxiv" as const, "substack" as const],
  citations: [
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
  ],
  quality_overall: 0.8,
  quality_floor: 0.5,
  would_exceed: false,
  search_query: "scaling orchestration citations",
};

describe("composeHtmlNativeCompetitionWriteTwinSearch", () => {
  it("HTML view + competition write twin search ready", () => {
    const c = composeHtmlNativeCompetitionWriteTwinSearch({
      session_id: "sess-1",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "html",
      operator_ack: true,
      competition: COMPETITION,
    });
    expect(c.html_view.pack_ready).toBe(true);
    expect(c.competition_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.pdf_primary).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.remote_index_queried).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "html_native_competition_write_twin_search_compose_advisory",
    );
    expect(formatHtmlNativeCompetitionWriteTwinSearchSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("PDF claimed format blocks HTML pack", () => {
    const c = composeHtmlNativeCompetitionWriteTwinSearch({
      session_id: "sess-2",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "pdf",
      operator_ack: true,
      competition: COMPETITION,
    });
    expect(c.html_view.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.pdf_primary).toBe(false);
  });

  it("budget would_exceed blocks competition path and pack", () => {
    const c = composeHtmlNativeCompetitionWriteTwinSearch({
      session_id: "sess-3",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "html",
      operator_ack: true,
      competition: {
        ...COMPETITION,
        would_exceed: true,
      },
    });
    expect(c.competition_pack.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeHtmlNativeCompetitionWriteTwinSearch({
      session_id: "sess-4",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      claimed_format: "html",
      operator_ack: false,
      competition: COMPETITION,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.twin_written).toBe(false);
  });
});
