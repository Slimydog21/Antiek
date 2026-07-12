import { describe, expect, it } from "vitest";
import {
  composeFloatingMultiselectWorkstationMarketplaceMo,
  formatFloatingMultiselectWorkstationMarketplaceMoSummary,
} from "./floatingMultiselectWorkstationMarketplaceMoCompose";

const MEMBERS = [
  {
    instance_id: "inst-a",
    parent_asset_id: "book-1",
    status: "open" as const,
    highlight: "scaling laws claim",
    prior_prompt: "What evidence supports the claim?",
    context: ["card-a"],
  },
  {
    instance_id: "inst-b",
    parent_asset_id: "book-1",
    status: "completed" as const,
    highlight: "counter-evidence",
    findings: ["finding-b1"],
  },
  {
    instance_id: "inst-c",
    parent_asset_id: "book-1",
    status: "proposed" as const,
    highlight: "third angle",
  },
];

const WORKSTATION_MARKETPLACE = {
  records: {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    records: [
      {
        record_id: "r1",
        kind: "insight" as const,
        body: "Power-law scaling holds in compute-optimal regimes",
      },
      {
        record_id: "r2",
        kind: "question" as const,
        body: "What residual gaps remain vs OpenAI DR?",
      },
    ],
    mark_for_prompt_context: true,
  },
  marketplace_research: {
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
  },
};

describe("composeFloatingMultiselectWorkstationMarketplaceMo", () => {
  it("multi-select + workstation marketplace ready", () => {
    const c = composeFloatingMultiselectWorkstationMarketplaceMo({
      multiselect: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        members: MEMBERS,
        selected_instance_ids: ["inst-a", "inst-b"],
        pack_mode: "cohesive_prompt",
        cohesive_prompt: "Synthesize A and B as one unit",
        extra_context: ["operator note"],
      },
      workstation_marketplace: WORKSTATION_MARKETPLACE,
      operator_ack: true,
    });
    expect(c.multiselect.pack_ready).toBe(true);
    expect(c.workstation_marketplace.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.purchase_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "floating_multiselect_workstation_marketplace_mo_compose_advisory",
    );
    expect(
      formatFloatingMultiselectWorkstationMarketplaceMoSummary(c),
    ).toMatch(/live_dispatched=false/);
  });

  it("operator_ack false blocks", () => {
    const c = composeFloatingMultiselectWorkstationMarketplaceMo({
      multiselect: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        members: MEMBERS,
        selected_instance_ids: ["inst-a", "inst-b"],
        pack_mode: "cohesive_prompt",
        cohesive_prompt: "Synthesize",
      },
      workstation_marketplace: WORKSTATION_MARKETPLACE,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("unattended false blocks workstation marketplace path", () => {
    const c = composeFloatingMultiselectWorkstationMarketplaceMo({
      multiselect: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        members: MEMBERS,
        selected_instance_ids: ["inst-a", "inst-b"],
        pack_mode: "cohesive_prompt",
        cohesive_prompt: "Synthesize",
      },
      workstation_marketplace: {
        ...WORKSTATION_MARKETPLACE,
        marketplace_research: {
          ...WORKSTATION_MARKETPLACE.marketplace_research,
          research: {
            ...WORKSTATION_MARKETPLACE.marketplace_research.research,
            mo_competition: {
              ...WORKSTATION_MARKETPLACE.marketplace_research.research
                .mo_competition,
              mo: {
                ...WORKSTATION_MARKETPLACE.marketplace_research.research
                  .mo_competition.mo,
                unattended_ack: false,
              },
            },
          },
        },
      },
      operator_ack: true,
    });
    expect(c.workstation_marketplace.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("collective_pack multi-select still pure", () => {
    const c = composeFloatingMultiselectWorkstationMarketplaceMo({
      multiselect: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        members: MEMBERS,
        selected_instance_ids: ["inst-a", "inst-b", "inst-c"],
        pack_mode: "collective_pack",
        cohesive_prompt: "Run as pack",
      },
      workstation_marketplace: WORKSTATION_MARKETPLACE,
      operator_ack: true,
    });
    expect(c.multiselect.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.pack_dispatched).toBe(false);
    expect(c.purchase_executed).toBe(false);
  });
});
