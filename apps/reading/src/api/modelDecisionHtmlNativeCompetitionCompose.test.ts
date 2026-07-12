import { describe, expect, it } from "vitest";
import {
  composeModelDecisionHtmlNativeCompetition,
  formatModelDecisionHtmlNativeCompetitionSummary,
} from "./modelDecisionHtmlNativeCompetitionCompose";

const COMPETITION_VIEW = {
  session_id: "sess-1",
  asset_id: "asset-1",
  html_projection_sha: "sha-html-1",
  view_requested: true,
  twin_bound: true,
  twin_substrate_ready: true,
  claimed_format: "html" as const,
  competition: {
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
  },
};

const DECISION = {
  selected_model_id: "gpt-5.5",
  models: [
    {
      model_id: "gpt-5.5",
      tier: "frontier",
      projected_cost_usd_high: 2,
      projected_cost_usd_low: 1,
    },
    {
      model_id: "grok-4.5",
      tier: "fast",
      projected_cost_usd_high: 0.5,
      projected_cost_usd_low: 0.2,
    },
  ],
  daily_cap_usd: 50,
  spent_usd: 10,
};

describe("composeModelDecisionHtmlNativeCompetition", () => {
  it("decision + HTML competition ready under budget", () => {
    const c = composeModelDecisionHtmlNativeCompetition({
      decision: DECISION,
      competition_view: COMPETITION_VIEW,
      operator_ack: true,
    });
    expect(c.decision.decision_ready).toBe(true);
    expect(c.competition_view.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_router_authorized).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.live_meter_read).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.pdf_primary).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.remote_index_queried).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.authority).toBe(
      "model_decision_html_native_competition_compose_advisory",
    );
    expect(formatModelDecisionHtmlNativeCompetitionSummary(c)).toMatch(
      /live_router_authorized=false/,
    );
  });

  it("would_exceed budget blocks pack", () => {
    const c = composeModelDecisionHtmlNativeCompetition({
      decision: {
        ...DECISION,
        spent_usd: 49,
        projected_cost_usd_high: 5,
        models: [
          {
            model_id: "gpt-5.5",
            tier: "frontier",
            projected_cost_usd_high: 5,
            projected_cost_usd_low: 4,
          },
        ],
      },
      competition_view: COMPETITION_VIEW,
      operator_ack: true,
    });
    expect(c.decision.would_exceed).toBe(true);
    expect(c.pack_ready).toBe(false);
    expect(c.live_router_authorized).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeModelDecisionHtmlNativeCompetition({
      decision: DECISION,
      competition_view: COMPETITION_VIEW,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("competition budget would_exceed blocks pack", () => {
    const c = composeModelDecisionHtmlNativeCompetition({
      decision: DECISION,
      competition_view: {
        ...COMPETITION_VIEW,
        competition: {
          ...COMPETITION_VIEW.competition,
          would_exceed: true,
        },
      },
      operator_ack: true,
    });
    expect(c.competition_view.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });
});
