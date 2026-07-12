import { describe, expect, it } from "vitest";
import {
  composeSettingsAddModelNdShadowCompetitionDrMo,
  formatSettingsAddModelNdShadowCompetitionDrMoSummary,
} from "./settingsAddModelNdShadowCompetitionDrMoCompose";

const WEEKLY_ND = {
  weekly_learn: {
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
  },
  nd_research: {
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
                approved_ceiling_usd: 50,
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
                        residual:
                          "strengthen collective floating cohesive pack",
                      },
                    ],
                    requested_families: [
                      "arxiv" as const,
                      "substack" as const,
                    ],
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
  },
};

const FULLSCREEN_PACK = {
  fullscreen: {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false,
  },
  weekly_nd: WEEKLY_ND,
};

const DRAFT_GATE = {
  session_id: "sess-1",
  parent_asset_id: "book-1",
  parent_excerpt: "<p>Parent body on scaling laws</p>",
  sources: [
    {
      instance_id: "float-1",
      parent_asset_id: "book-1",
      status: "completed" as const,
      highlight: "key claim",
      findings: ["evidence A"],
    },
  ],
  stage: "draft_only" as const,
};
const RESEARCH_PACK = {
  draft_gate: DRAFT_GATE,
  fullscreen_pack: FULLSCREEN_PACK,
};

const SETTINGS = {
  models: [
    { model_id: "gpt-5.5", provider: "openai" },
    { model_id: "grok-4.5", provider: "xai" },
  ],
  pending_add_model_ids: ["mimo-v2"],
  action: "preview" as const,
  daily_cap_usd: 25,
  spent_usd: 4,
  selected_model_id: "gpt-5.5",
  projected_cost_usd_high: 2,
  projected_cost_usd_low: 1,
};
const WRITE = {
  session_id: "sess-1",
  draft_id: "draft-1",
  parent_asset_id: "book-1",
  twin_slices: [
    {
      parent_asset_id: "asset-1",
      insights: ["scaling claim holds in compute-optimal regimes"],
      questions: ["Where does it break?"],
    },
    {
      parent_asset_id: "asset-2",
      insights: ["attention efficiency tradeoffs"],
      questions: [],
    },
  ],
  base_draft_html: "<p>Opening paragraph</p>",
  chase_slots: [
    {
      slot_id: "s1",
      question_id: "q1",
      parent_asset_id: "book-1",
      status: "completed" as const,
      findings: ["finding A from chase"],
      body: "What evidence supports scaling?",
    },
    {
      slot_id: "s2",
      question_id: "q2",
      parent_asset_id: "book-1",
      status: "completed" as const,
      findings: ["finding B from chase"],
      body: "Counter-evidence?",
    },
  ],
  analysis_kind: "draft_analysis" as const,
};
const MO = {
  operator_id: "op-1",
  work_minutes: 120,
  goals: [
    { goal_id: "g1", title: "Map scaling literature" },
    { goal_id: "g2", title: "Synthesize open problems" },
  ],
  usd_per_hour: 30,
  price_ceiling_ack: true,
  stage: "recommend_only" as const,
};
const TWIN = {
  parent_asset_id: "book-1",
  source_excerpt: "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
  focus_questions: ["Where does it break?", "What residual gaps?"],
};
const HTML_VIEW = {
  session_id: "sess-1",
  asset_id: "book-1",
  html_projection_sha: "sha-html-ready",
  view_requested: true,
  twin_bound: true,
  twin_substrate_ready: true,
  claimed_format: "html" as const,
};
const RECORD_PROMPT = {
  session_id: "sess-1",
  parent_asset_id: "book-1",
  records: [
    {
      record_id: "r1",
      kind: "insight" as const,
      body: "scaling holds under noise",
      source_ref: "book-1",
    },
    {
      record_id: "r2",
      kind: "question" as const,
      body: "What is the failure mode?",
    },
  ],
  user_prompt: "Summarize open questions from the pack",
  selected_model_id: "gpt-5",
  models: [
    {
      model_id: "gpt-5",
      tier: "frontier",
      projected_cost_usd_high: 2,
      projected_cost_usd_low: 1,
    },
    {
      model_id: "composer-2.5",
      tier: "workhorse",
      projected_cost_usd_high: 0.5,
    },
  ],
  daily_cap_usd: 100,
  spent_usd: 40,
  projected_cost_usd_high: 2,
  projected_cost_usd_low: 1,
};
const SOURCES = {
  session_id: "sess-1",
  parent_asset_id: "book-1",
  requested_families: ["arxiv", "substack"] as const,
  sources: [
    {
      source_id: "arx-1",
      family: "arxiv" as const,
      title: "Scaling Laws for Neural Language Models",
      external_id: "arxiv:2001.08361",
      html_fragment: "<article>abstract…</article>",
    },
    {
      source_id: "sub-1",
      family: "substack" as const,
      title: "The Batch essay",
      external_id: "substack:thebatch",
      url: "https://example.substack.com/p/x",
      html_fragment: "<article>essay…</article>",
    },
  ],
  quality_overall: 0.85,
  quality_floor: 0.7,
  would_exceed: false,
};
const MARKET = {
  title: "Scaling Laws Book",
  account_id: "acct-1",
  free_copy_available: true as boolean | null,
  free_html_projection_sha: "sha-free-1",
  purchase_ack: false,
  port_requested: true,
};

const RESEARCH = {
  sources: SOURCES,
  record_html: {
    record_prompt: RECORD_PROMPT,
    html_pack: {
      html_view: HTML_VIEW,
      twin_mo: {
        twin: TWIN,
        mo_write: {
          mo: MO,
          research_write: {
            write: WRITE,
            settings_research: {
              settings: SETTINGS,
              research_pack: RESEARCH_PACK,
            },
          },
        },
      },
    },
  },
};
const WEEKLY_LEARN = {
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

const MARKET_RESEARCH = {
  market: MARKET,
  research: RESEARCH,
};
const ND_SHADOW = {
  selected_model_id: "gpt-5",
  nd_recommended_model_id: "claude-opus",
  kill_switch_on: true,
  confidence: 0.72,
  task: "deep_research",
  inventory_model_ids: ["gpt-5", "claude-opus", "mimo"],
};

const WEEKLY_MARKET = {
  weekly_learn: WEEKLY_LEARN,
  market_research: MARKET_RESEARCH,
};
const COMPETITION = {
  session_id: "sess-1",
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
  requested_families: ["arxiv", "substack"] as const,
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
};
























describe("composeSettingsAddModelNdShadowCompetitionDrMo", () => {






  const twin_pack = {
    twin: {
      parent_asset_id: "book-1",
      source_excerpt:
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
      focus_questions: ["Where does it break?", "What residual gaps?"],
    },
    settings_pack: {
      settings: {
        models: [
          { model_id: "gpt-5.5", provider: "openai" },
          { model_id: "grok-4.5", provider: "xai" },
        ],
        pending_add_model_ids: ["mimo-v2"],
        action: "preview" as const,
        daily_cap_usd: 25,
        spent_usd: 4,
        selected_model_id: "gpt-5.5",
        projected_cost_usd_high: 2,
        projected_cost_usd_low: 1,
      },
      fullscreen_mo: {
        fullscreen: {
          session_id: "sess-1",
          parent_asset_id: "book-1",
          highlight: "Scaling laws claim from page 12",
          prompt: "What evidence supports this?",
          gated: false,
        },
        mo_pack: {
          mo: {
            operator_id: "op-1",
            work_minutes: 120,
            goals: [
              { goal_id: "g1", title: "Map scaling literature" },
              { goal_id: "g2", title: "Synthesize open problems" },
            ],
            usd_per_hour: 30,
            price_ceiling_ack: true,
            stage: "recommend_only" as const,
          },
          draft_multi: {
            draft_gate: {
              session_id: "sess-1",
              parent_asset_id: "book-1",
              parent_excerpt: "<p>Parent body on scaling laws</p>",
              sources: [
                {
                  instance_id: "float-1",
                  parent_asset_id: "book-1",
                  status: "completed" as const,
                  highlight: "key claim",
                  findings: ["evidence A"],
                },
              ],
              stage: "draft_only" as const,
            },
            multi_pack: {
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
              record_write: {
                record_prompt: {
                  session_id: "sess-1",
                  parent_asset_id: "book-1",
                  records: [
                    {
                      record_id: "r1",
                      kind: "insight" as const,
                      body: "scaling holds under noise",
                      source_ref: "book-1",
                    },
                    {
                      record_id: "r2",
                      kind: "question" as const,
                      body: "What is the failure mode?",
                    },
                  ],
                  user_prompt: "Summarize open questions from the pack",
                  selected_model_id: "gpt-5",
                  models: [
                    {
                      model_id: "gpt-5",
                      tier: "frontier",
                      projected_cost_usd_high: 2,
                      projected_cost_usd_low: 1,
                    },
                  ],
                  daily_cap_usd: 100,
                  spent_usd: 40,
                  projected_cost_usd_high: 2,
                  projected_cost_usd_low: 1,
                },
                write_pack: {
                  write: {
                    session_id: "sess-1",
                    draft_id: "draft-1",
                    parent_asset_id: "book-1",
                    twin_slices: [
                      {
                        parent_asset_id: "asset-1",
                        insights: ["scaling claim holds"],
                        questions: ["Where does it break?"],
                      },
                      {
                        parent_asset_id: "asset-2",
                        insights: ["attention efficiency"],
                        questions: [] as string[],
                      },
                    ],
                    chase_slots: [
                      {
                        slot_id: "s1",
                        question_id: "q1",
                        parent_asset_id: "book-1",
                        status: "completed" as const,
                        findings: ["finding A"],
                        body: "Evidence?",
                      },
                      {
                        slot_id: "s2",
                        question_id: "q2",
                        parent_asset_id: "book-1",
                        status: "completed" as const,
                        findings: ["finding B"],
                        body: "Counter?",
                      },
                    ],
                    analysis_kind: "draft_analysis" as const,
                  },
                  highlight_pack: {
                    highlight: {
                      parent_asset_id: "book-1",
                      highlight: "scaling orchestration residual under noise",
                      gated: false as const,
                      would_exceed: false as boolean | null,
                      preferred_view_mode: "floating" as const,
                      source_families: ["arxiv", "substack"] as (
                        | "arxiv"
                        | "substack"
                      )[],
                    },
                    twin_search_pack: {
                      competition_pack: {
                        competition: COMPETITION,
                        nd_weekly: {
                          nd_shadow: ND_SHADOW,
                          weekly_market: WEEKLY_MARKET,
                        },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  };

  const html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-html-ready",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const weekly_learn = {
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

  const decision = {
    selected_model_id: "gpt-5.5",
    models: [
      {
        model_id: "gpt-5.5",
        tier: "frontier",
        projected_cost_usd_high: 2,
        projected_cost_usd_low: 1,
      },
      {
        model_id: "composer-2.5",
        tier: "workhorse",
        projected_cost_usd_high: 0.5,
      },
    ],
    daily_cap_usd: 50,
    spent_usd: 10,
    projected_cost_usd_high: 2,
    projected_cost_usd_low: 1,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"],
  };

  const sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as const,
    sources: [
      {
        source_id: "arx-1",
        family: "arxiv" as const,
        title: "Scaling Laws under Noise",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "sub-1",
        family: "substack" as const,
        title: "Research notes on evals",
        external_id: "substack:evals",
        url: "https://example.substack.com/p/evals",
        html_fragment: "<article>essay…</article>",
      },
    ],
  };

  const mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map arxiv competition gaps" },
      { goal_id: "g2", title: "Synthesize twin notes" },
    ],
    usd_per_hour: 30,
    // Must be ≥ recommended (work_minutes/60 * usd_per_hour * intensity).
    approved_ceiling_usd: 500,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const bench = {
    week_id: "2026-W28",
    focus_task: "deep_research",
    events: [
      {
        event_id: "e1",
        task: "deep_research",
        model_id: "gpt-5.5",
        outcome: "worked" as const,
        score: 0.9,
      },
      {
        event_id: "e2",
        task: "deep_research",
        model_id: "gpt-5.5",
        outcome: "worked" as const,
        score: 0.85,
      },
      {
        event_id: "e3",
        task: "deep_research",
        model_id: "mimo-v2",
        outcome: "failed" as const,
        score: 0.2,
      },
      {
        event_id: "e4",
        task: "deep_research",
        model_id: "mimo-v2",
        outcome: "failed" as const,
        score: 0.3,
      },
      {
        event_id: "e5",
        task: "twin_notes",
        model_id: "grok-4.5",
        outcome: "worked" as const,
        score: 0.8,
      },
      {
        event_id: "e6",
        task: "twin_notes",
        model_id: "grok-4.5",
        outcome: "worked" as const,
        score: 0.75,
      },
    ],
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    daily_cap_usd: 20,
    spent_usd: 5,
    projected_cost_usd_high: 0.5,
    existing_tasks: ["deep_research", "twin_notes"],
  };

  const market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
  };

  const twin_records = [
    {
      twin_id: "twin-book-1",
      parent_asset_id: "book-1",
      insights: ["scaling laws hold under noise in compute-optimal regimes"],
      questions: ["Where does scaling break under distribution shift?"],
      source_label: "book-1-twin",
    },
    {
      twin_id: "twin-arxiv-1",
      parent_asset_id: "cite-parent-c1",
      insights: ["Scaling Laws under Noise"],
      questions: ["How does arxiv residual inform Antiek DR?"],
      source_label: "arxiv",
    },
  ];

  const competition = {
    session_id: "sess-1",
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
    requested_families: ["arxiv", "substack"] as const,
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
    would_exceed: false as boolean | null,
  };



  const competition_pack_input = {
    competition,
    free_pack: {
      market,
      bench_mo: {
        bench,
        mo_pack: {
          mo,
          research_pack: {
            sources,
            decision_pack: {
              decision,
              twin_search_pack: {
                search_query: "scaling laws noise",
                twin_records,
                weekly_html: {
                  weekly_learn,
                  html_pack: { html_view, twin_pack },
                },
              },
            },
          },
        },
      },
    },
  };

  const twin_input = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1",
  };

  const presentation_input = {
    view_mode: "side_panel" as const,
    open_requested: true,
    merge_to_parent_preview: false,
    presented_insights: [
      "scaling laws hold under noise in compute-optimal regimes",
    ],
    presented_questions: [
      "Where does scaling break under distribution shift?",
    ],
  };


  const nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };


  const nd_twin = {
    nd_shadow,
    twin_presentation: {
      twin: twin_input,
      presentation: presentation_input,
      competition_pack: competition_pack_input,
    },
  };

  // Free-first path: free available → gate_ready without purchase
  const purchase_free = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
    list_price_usd: 10 as number | null,
    approved_spend_usd: 20 as number | null,
    remaining_budget_usd: 50 as number | null,
  };

  const paid_nd = {
    purchase: purchase_free,
    nd_twin,
  };

  const collective = {
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
    cohesive_prompt: "Synthesize presented twin instances A and B as one unit",
  };


  // paid_nd + collective from fixtures
  const collective_pack = { collective, paid_nd };

  const draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "float-1",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "key claim",
        findings: ["evidence A"],
      },
    ],
    stage: "draft_only" as const,
  };


  const draft_collective = {
    draft_gate,
    collective_pack,
  };

  const fullscreen_open = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const fullscreen_pack = {
    fullscreen: fullscreen_open,
    draft_collective,
  };

  const mo_unattended = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map arxiv competition gaps" },
      { goal_id: "g2", title: "Synthesize twin notes" },
    ],
    usd_per_hour: 15,
    approved_ceiling_usd: 50,
    unattended_ack: true,
    spend_consent: true,
    brief_dispatch_ready: true,
  };


  const mo_pack = {
    mo: mo_unattended,
    fullscreen_pack,
  };

  const decision_input = {
    selected_model_id: "gpt-5.5",
    models: [
      {
        model_id: "gpt-5.5",
        tier: "frontier",
        projected_cost_usd_high: 2,
        projected_cost_usd_low: 1,
      },
      {
        model_id: "composer-2.5",
        tier: "workhorse",
        projected_cost_usd_high: 0.5,
      },
    ],
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };


  const settings_mo = {
    decision: decision_input,
    mo_pack,
  };

  const sources_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as const,
    sources: [
      {
        source_id: "arx-1",
        family: "arxiv" as const,
        title: "Scaling Laws under Noise",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "sub-1",
        family: "substack" as const,
        title: "Research notes on evals",
        external_id: "substack:evals",
        url: "https://example.substack.com/p/evals",
        html_fragment: "<article>essay…</article>",
      },
    ],
  };


  const source_pack = {
    sources: sources_input,
    settings_mo,
  };

  const bench_input = {
    week_id: "2026-W28",
    focus_task: "deep_research",
    events: [
      {
        event_id: "e1",
        task: "deep_research",
        model_id: "gpt-5.5",
        outcome: "worked" as const,
        score: 0.9,
      },
      {
        event_id: "e2",
        task: "deep_research",
        model_id: "gpt-5.5",
        outcome: "worked" as const,
        score: 0.85,
      },
      {
        event_id: "e3",
        task: "deep_research",
        model_id: "mimo-v2",
        outcome: "failed" as const,
        score: 0.2,
      },
      {
        event_id: "e4",
        task: "deep_research",
        model_id: "mimo-v2",
        outcome: "failed" as const,
        score: 0.3,
      },
      {
        event_id: "e5",
        task: "twin_notes",
        model_id: "grok-4.5",
        outcome: "worked" as const,
        score: 0.8,
      },
      {
        event_id: "e6",
        task: "twin_notes",
        model_id: "grok-4.5",
        outcome: "worked" as const,
        score: 0.75,
      },
    ],
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };


  const settings_input = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2", "composer-2.5"],
    action: "propose_add" as const,
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    selected_model_id: "gpt-5.5",
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
  };


  const competition_input = {
    session_id: "sess-1",
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
    requested_families: ["arxiv", "substack"] as const,
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
    quality_overall: 0.85 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };


  const market_input = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
  };


  const twin_note_input = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1",
  };


  const html_view_input = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-html-ready",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };


  const search_twin_records = [
    {
      twin_id: "twin-book-1",
      parent_asset_id: "book-1",
      insights: ["scaling laws hold under noise in compute-optimal regimes"],
      questions: ["Where does scaling break under distribution shift?"],
      source_label: "book-1-twin",
    },
    {
      twin_id: "twin-arxiv-1",
      parent_asset_id: "cite-parent-c1",
      insights: ["Scaling Laws under Noise"],
      questions: ["How does arxiv residual inform Antiek DR?"],
      source_label: "arxiv",
    },
  ];


  const decision_budget_input = {
    selected_model_id: "gpt-5.5",
    models: [
      {
        model_id: "gpt-5.5",
        tier: "frontier",
        projected_cost_usd_high: 2,
        projected_cost_usd_low: 1,
      },
      {
        model_id: "composer-2.5",
        tier: "workhorse",
        projected_cost_usd_high: 0.5,
      },
    ],
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const model_decision_pack = {
    decision: decision_budget_input,
    twin_search_pack: {
      search_query: "scaling noise",
      twin_records: search_twin_records,
      html_pack: {
        html_view: html_view_input,
        twin_pack: {
          twin: twin_note_input,
          market_pack: {
            market: market_input,
            competition_pack: {
              competition: competition_input,
              settings_pack: {
                settings: settings_input,
                bench_pack: {
                  bench: bench_input,
                  source_pack,
                },
              },
            },
          },
        },
      },
    },
  };

  const rewrite_ready = {
    week_label: "2026-W28",
    patterns: [
      {
        task_family: "deep_research",
        model_id: "gpt-5",
        outcome: "failed" as const,
        n: 3,
      },
      {
        task_family: "deep_research",
        model_id: "mimo-v2",
        outcome: "mixed" as const,
        n: 2,
      },
      {
        task_family: "twin_notes",
        model_id: "claude",
        outcome: "worked" as const,
        n: 4,
      },
    ],
  };

  const rewrite_empty = {
    week_label: "2026-W28",
    patterns: [
      {
        task_family: "twin_notes",
        model_id: "claude",
        outcome: "worked" as const,
        n: 4,
      },
    ],
  };

  const attach_sources_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as const,
    sources: [
      {
        source_id: "arx-1",
        family: "arxiv" as const,
        title: "Scaling Laws under Noise",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "sub-1",
        family: "substack" as const,
        title: "Research notes on evals",
        external_id: "substack:evals",
        url: "https://example.substack.com/p/evals",
        html_fragment: "<article>essay…</article>",
      },
    ],
  };

  const rewrite_pack = {
    rewrite: rewrite_ready,
    model_decision_pack,
  };

  const mo_ready = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map arxiv competition gaps" },
      { goal_id: "g2", title: "Synthesize twin notes" },
    ],
    usd_per_hour: 15,
    approved_ceiling_usd: 50,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const research_pack = {
    sources: attach_sources_input,
    rewrite_pack,
  };

  const competition_dr_input = {
    session_id: "sess-1",
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
    requested_families: ["arxiv", "substack"] as const,
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
    quality_overall: 0.85 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const mo_pack_input = {
    mo: mo_ready,
    research_pack,
  };

  const nd_shadow_input = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const competition_pack = {
    competition: competition_dr_input,
    mo_pack: mo_pack_input,
  };

  const settings_add_input = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2", "composer-2.5"],
    action: "propose_add" as const,
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    selected_model_id: "gpt-5.5",
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
  };

  const nd_pack = {
    nd_shadow: nd_shadow_input,
    competition_pack,
  };

  it("settings add-model + ND shadow competition DR MO pack ready", () => {
    const c = composeSettingsAddModelNdShadowCompetitionDrMo({
      settings: settings_add_input,
      nd_pack,
      operator_ack: true,
    });
    expect(c.settings.pack_ready).toBe(true);
    expect(c.settings.proposed_new_count).toBeGreaterThanOrEqual(1);
    expect(c.nd_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.authority).toBe(
      "settings_add_model_nd_shadow_competition_dr_mo_compose_advisory",
    );
    expect(
      formatSettingsAddModelNdShadowCompetitionDrMoSummary(c),
    ).toMatch(/secrets_stored=false/);
  });

  it("operator_ack false blocks", () => {
    const c = composeSettingsAddModelNdShadowCompetitionDrMo({
      settings: settings_add_input,
      nd_pack,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("would_exceed on nested competition blocks overall", () => {
    const c = composeSettingsAddModelNdShadowCompetitionDrMo({
      settings: settings_add_input,
      nd_pack: {
        nd_shadow: nd_shadow_input,
        competition_pack: {
          competition: { ...competition_dr_input, would_exceed: true },
          mo_pack: mo_pack_input,
        },
      },
      operator_ack: true,
    });
    expect(c.nd_pack.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("preview with no new models still ready when inventory valid", () => {
    const c = composeSettingsAddModelNdShadowCompetitionDrMo({
      settings: {
        ...settings_add_input,
        action: "preview" as const,
        pending_add_model_ids: [],
      },
      nd_pack,
      operator_ack: true,
    });
    expect(c.settings.pack_ready).toBe(true);
    expect(c.nd_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.inventory_mutated).toBe(false);
    expect(c.secrets_stored).toBe(false);
  });
});
