import { describe, expect, it } from "vitest";
import {
  composeAntiekBenchWeeklyNdMultiselectMo,
  formatAntiekBenchWeeklyNdMultiselectMoSummary,
} from "./antiekBenchWeeklyNdMultiselectMoCompose";

const ND_RESEARCH = {
  nd_shadow: {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    inventory_model_ids: ["gpt-5.5", "claude-opus"],
    task: "deep_research",
  },
  research_pack: {
    multiselect: {
      session_id: "sess-1",
      parent_asset_id: "book-1",
      members: [
        {
          instance_id: "inst-a",
          parent_asset_id: "book-1",
          status: "open" as const,
          highlight: "scaling laws claim",
        },
        {
          instance_id: "inst-b",
          parent_asset_id: "book-1",
          status: "completed" as const,
          highlight: "counter-evidence",
          findings: ["finding-b1"],
        },
      ],
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt" as const,
      cohesive_prompt: "Synthesize A and B as one unit",
    },
    workstation_marketplace: {
      records: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        records: [
          {
            record_id: "r1",
            kind: "insight" as const,
            body: "Power-law scaling holds",
          },
          {
            record_id: "r2",
            kind: "question" as const,
            body: "What residual gaps remain?",
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
    },
  },
};

const WEEKLY = {
  week_id: "2026-W28",
  min_events_per_task: 2,
  events: [
    {
      event_id: "e1",
      task: "deep_research",
      model_id: "gpt-5",
      outcome: "failed" as const,
    },
    {
      event_id: "e2",
      task: "deep_research",
      model_id: "gpt-5",
      outcome: "failed" as const,
    },
    {
      event_id: "e3",
      task: "twin_notes",
      model_id: "claude",
      outcome: "worked" as const,
    },
    {
      event_id: "e4",
      task: "twin_notes",
      model_id: "claude",
      outcome: "worked" as const,
    },
  ],
};

describe("composeAntiekBenchWeeklyNdMultiselectMo", () => {
  it("weekly learn + ND multi-select research ready", () => {
    const c = composeAntiekBenchWeeklyNdMultiselectMo({
      weekly_learn: WEEKLY,
      nd_research: ND_RESEARCH,
      operator_ack: true,
    });
    expect(c.weekly_learn.learn_ready).toBe(true);
    expect(c.weekly_learn.proposal_count).toBe(2);
    expect(c.nd_research.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.backlog_mutated).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.live_router_authorized).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.purchase_executed).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "antiek_bench_weekly_nd_multiselect_mo_compose_advisory",
    );
    expect(formatAntiekBenchWeeklyNdMultiselectMoSummary(c)).toMatch(
      /backlog_mutated=false/,
    );
  });

  it("operator_ack false blocks", () => {
    const c = composeAntiekBenchWeeklyNdMultiselectMo({
      weekly_learn: WEEKLY,
      nd_research: ND_RESEARCH,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("sparse weekly events block learn_ready and pack", () => {
    const c = composeAntiekBenchWeeklyNdMultiselectMo({
      weekly_learn: {
        week_id: "2026-W28",
        min_events_per_task: 5,
        events: [
          {
            event_id: "e1",
            task: "deep_research",
            model_id: "gpt-5",
            outcome: "failed",
          },
        ],
      },
      nd_research: ND_RESEARCH,
      operator_ack: true,
    });
    expect(c.weekly_learn.learn_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.store_mutated).toBe(false);
  });

  it("unattended false blocks nd research path", () => {
    const c = composeAntiekBenchWeeklyNdMultiselectMo({
      weekly_learn: WEEKLY,
      nd_research: {
        ...ND_RESEARCH,
        research_pack: {
          ...ND_RESEARCH.research_pack,
          workstation_marketplace: {
            ...ND_RESEARCH.research_pack.workstation_marketplace,
            marketplace_research: {
              ...ND_RESEARCH.research_pack.workstation_marketplace
                .marketplace_research,
              research: {
                ...ND_RESEARCH.research_pack.workstation_marketplace
                  .marketplace_research.research,
                mo_competition: {
                  ...ND_RESEARCH.research_pack.workstation_marketplace
                    .marketplace_research.research.mo_competition,
                  mo: {
                    ...ND_RESEARCH.research_pack.workstation_marketplace
                      .marketplace_research.research.mo_competition.mo,
                    unattended_ack: false,
                  },
                },
              },
            },
          },
        },
      },
      operator_ack: true,
    });
    expect(c.nd_research.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });
});
