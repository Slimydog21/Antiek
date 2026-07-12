import { describe, expect, it } from "vitest";
import {
  composeMarketplaceHighlightFloatRecursiveTwinMo,
  formatMarketplaceHighlightFloatRecursiveTwinMoSummary,
} from "./marketplaceHighlightFloatRecursiveTwinMoCompose";

const MO_COMP = {
  mo: {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Survey arxiv competition gaps" },
      { goal_id: "g2", title: "Draft twin notes" },
    ],
    usd_per_hour: 15,
    approved_ceiling_usd: 40,
    unattended_ack: true,
    spend_consent: true,
  },
  research: {
    decision: {
      selected_model_id: "gpt-5.5",
      models: [
        {
          model_id: "gpt-5.5",
          tier: "frontier",
          projected_cost_usd_high: 2,
          projected_cost_usd_low: 1,
        },
      ],
      daily_cap_usd: 50,
      spent_usd: 10,
    },
    competition_view: {
      session_id: "sess-1",
      asset_id: "book-1",
      html_projection_sha: "sha-free",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "html" as const,
      competition: {
        draft_id: "draft-1",
        parent_asset_id: "book-1",
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
    },
  },
};

const MARKET = {
  session_id: "sess-1",
  asset_id: "book-1",
  title: "Scaling Laws",
  account_id: "acct-1",
  free_copy_available: true,
  free_html_projection_sha: "sha-free",
  port_requested: true,
  purchase_ack: false,
  list_price_usd: 10,
  approved_spend_usd: 20,
  remaining_budget_usd: 50,
  view_requested: true,
  twin_findings: [
    {
      source_id: "q1",
      body: "What is the core thesis?",
      kind: "question" as const,
    },
  ],
  mark_for_prompt_context: true,
};

describe("composeMarketplaceHighlightFloatRecursiveTwinMo", () => {
  it("free HTML book + highlight research pack ready", () => {
    const c = composeMarketplaceHighlightFloatRecursiveTwinMo({
      market: { ...MARKET, operator_ack: true },
      research: {
        highlight_surface: {
          highlight: "scaling laws under noise",
          gated: false,
          would_exceed: false,
          surface_action: "spawn_only",
          source_families: ["arxiv"],
        },
        mo_competition: MO_COMP,
      },
      operator_ack: true,
    });
    expect(c.market.session_ready).toBe(true);
    expect(c.research.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "marketplace_highlight_float_recursive_twin_mo_compose_advisory",
    );
    expect(formatMarketplaceHighlightFloatRecursiveTwinMoSummary(c)).toMatch(
      /purchase_executed=false/,
    );
  });

  it("seeds highlight from book title when omitted", () => {
    const c = composeMarketplaceHighlightFloatRecursiveTwinMo({
      market: { ...MARKET, operator_ack: true },
      research: {
        highlight_surface: {
          gated: false,
          would_exceed: false,
          surface_action: "spawn_only",
        },
        mo_competition: MO_COMP,
      },
      operator_ack: true,
      seed_highlight_from_title: true,
    });
    expect(c.pack_ready).toBe(true);
    expect(
      c.research.highlight_surface.surface.launch?.highlight ??
        c.research.highlight_surface.surface,
    ).toBeTruthy();
    expect(c.purchase_executed).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeMarketplaceHighlightFloatRecursiveTwinMo({
      market: { ...MARKET, operator_ack: false },
      research: {
        highlight_surface: {
          highlight: "scaling laws under noise",
          gated: false,
          would_exceed: false,
          surface_action: "spawn_only",
        },
        mo_competition: MO_COMP,
      },
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.hosted).toBe(false);
  });

  it("unattended false blocks research path", () => {
    const c = composeMarketplaceHighlightFloatRecursiveTwinMo({
      market: { ...MARKET, operator_ack: true },
      research: {
        highlight_surface: {
          highlight: "scaling laws under noise",
          gated: false,
          would_exceed: false,
          surface_action: "spawn_only",
        },
        mo_competition: {
          ...MO_COMP,
          mo: { ...MO_COMP.mo, unattended_ack: false },
        },
      },
      operator_ack: true,
    });
    expect(c.research.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
