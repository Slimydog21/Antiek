import { describe, expect, it } from "vitest";
import {
  composeWorkstationInsightMarketplaceHighlightMo,
  formatWorkstationInsightMarketplaceHighlightMoSummary,
} from "./workstationInsightMarketplaceHighlightMoCompose";

const MARKET_RESEARCH = {
  market: {
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
  },
  research: {
    highlight_surface: {
      highlight: "scaling laws under noise",
      gated: false,
      would_exceed: false,
      surface_action: "spawn_only" as const,
      source_families: ["arxiv" as const],
    },
    mo_competition: {
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
          claimed_format: "html" as const,
          competition: {
            draft_id: "draft-1",
            parent_asset_id: "book-1",
            competitor_decisions: [
              {
                competitor: "Perplexity",
                area: "citation_grounding" as const,
                decision_summary: "Inline citations",
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
            would_exceed: false,
            search_query: "scaling orchestration",
          },
        },
      },
    },
  },
};

describe("composeWorkstationInsightMarketplaceHighlightMo", () => {
  it("records + marketplace research ready", () => {
    const c = composeWorkstationInsightMarketplaceHighlightMo({
      records: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        records: [
          {
            record_id: "r1",
            kind: "insight",
            body: "Power-law scaling holds in compute-optimal regimes",
          },
          {
            record_id: "r2",
            kind: "question",
            body: "What residual gaps remain vs OpenAI DR?",
          },
        ],
        operator_ack: true,
        mark_for_prompt_context: true,
      },
      marketplace_research: MARKET_RESEARCH,
      operator_ack: true,
    });
    expect(c.records.record_ready).toBe(true);
    expect(c.marketplace_research.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.purchase_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "workstation_insight_marketplace_highlight_mo_compose_advisory",
    );
    expect(formatWorkstationInsightMarketplaceHighlightMoSummary(c)).toMatch(
      /record_persisted=false/,
    );
  });

  it("empty records fail closed", () => {
    expect(() =>
      composeWorkstationInsightMarketplaceHighlightMo({
        records: {
          session_id: "sess-1",
          parent_asset_id: "book-1",
          records: [],
          operator_ack: true,
        },
        marketplace_research: MARKET_RESEARCH,
        operator_ack: true,
      }),
    ).toThrow(/records must be a non-empty array/);
  });

  it("operator_ack false blocks", () => {
    const c = composeWorkstationInsightMarketplaceHighlightMo({
      records: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        records: [
          { record_id: "r1", kind: "insight", body: "A" },
        ],
        operator_ack: false,
      },
      marketplace_research: MARKET_RESEARCH,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });

  it("unattended false blocks marketplace research path", () => {
    const c = composeWorkstationInsightMarketplaceHighlightMo({
      records: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        records: [
          { record_id: "r1", kind: "insight", body: "A" },
        ],
        operator_ack: true,
      },
      marketplace_research: {
        ...MARKET_RESEARCH,
        research: {
          ...MARKET_RESEARCH.research,
          mo_competition: {
            ...MARKET_RESEARCH.research.mo_competition,
            mo: {
              ...MARKET_RESEARCH.research.mo_competition.mo,
              unattended_ack: false,
            },
          },
        },
      },
      operator_ack: true,
    });
    expect(c.marketplace_research.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
