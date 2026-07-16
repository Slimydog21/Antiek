import { describe, expect, it } from "vitest";
import {
  composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack,
  formatMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackSummary,
} from "./mktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose";

describe("composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack", () => {
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





























const bench_models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
  { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
];

function eventsDeepResearch() {
  return [
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
  ];
}



const COMPETITOR_DECISIONS = [
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

const COMPETITION_CITATIONS = [
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

  const market_free = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
  };

  const settings_pack = {
    settings: settings_add_input,
    nd_pack,
  };

  const html_view_auth_input = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-html-ready",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const market_pack = {
    market: market_free,
    settings_pack,
  };

  const twin_search_records = [
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

  const html_pack = {
    html_view: html_view_auth_input,
    market_pack,
  };

  const decision_outer_input = {
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

  const twin_search_pack = {
    search_query: "scaling noise",
    twin_records: twin_search_records,
    html_pack,
  };

  const multiselect_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit over twin search + budget",
  };

  const decision_pack = {
    decision: decision_outer_input,
    twin_search_pack,
  };

  const multi_pack = {
    multiselect: multiselect_input,
    decision_pack,
  };

  const draft_gate_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent scaling laws body</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const draft_pack = {
    draft_gate: draft_gate_input,
    multi_pack,
  };

  const fullscreen_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const outer_fullscreen_pack = {
    fullscreen: fullscreen_input,
    draft_pack,
  };

  const mo_input = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling-law residual gaps" },
      { goal_id: "g2", title: "Synthesize twin search hits" },
    ],
    usd_per_hour: 15,
    // Must be ≥ recommended (work_minutes/60 * usd_per_hour * intensity).
    approved_ceiling_usd: 50,
    unattended_ack: true,
    spend_consent: true,
    brief_dispatch_ready: true,
  };

  const outer_mo_pack = {
    mo: mo_input,
    fullscreen_pack: outer_fullscreen_pack,
  };

  const outer_bench_input = {
    week_id: "2026-W28",
    focus_task: "deep_research",
    events: eventsDeepResearch(),
    models: bench_models,
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const recommend_pack = {
    bench: outer_bench_input,
    mo_pack: outer_mo_pack,
  };

  const outer_sources_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as const,
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling Laws for Neural Language Models",
        external_id: "arxiv:2001.08361",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Evals that matter",
        external_id: "substack:evals",
        url: "https://example.substack.com/p/evals",
      },
    ],
  };

  const outer_source_pack = {
    sources: outer_sources_input,
    recommend_pack,
  };

  const outer_competition_input = {
    session_id: "sess-1",
    competitor_decisions: COMPETITOR_DECISIONS,
    requested_families: ["arxiv", "substack"] as const,
    citations: COMPETITION_CITATIONS,
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const outer_twin_input = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1",
  };

  const outer_presentation_input = {
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

  const outer_competition_pack = {
    competition: outer_competition_input,
    source_pack: outer_source_pack,
  };

  const outer_nd_shadow_input = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const twin_presentation = {
    twin: outer_twin_input,
    presentation: outer_presentation_input,
    competition_pack: outer_competition_pack,
  };

  const outer_settings_input = {
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

  const outer_nd_pack = {
    nd_shadow: outer_nd_shadow_input,
    twin_presentation: {
      twin: outer_twin_input,
      presentation: outer_presentation_input,
      competition_pack: outer_competition_pack,
    },
  };


  const outer_market_input = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
  };

  const outer_settings_pack = {
    settings: outer_settings_input,
    nd_pack: outer_nd_pack,
  };


  const outer_html_view_input = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-html-ready",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const outer_market_pack = {
    market: outer_market_input,
    settings_pack: outer_settings_pack,
  };

  const outer_twin_records = [
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

  const outer_html_pack = {
    html_view: outer_html_view_input,
    market_pack: outer_market_pack,
  };

  const pack_outer_decision_input = {
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

  const pack_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: outer_twin_records,
    html_pack: outer_html_pack,
  };

  const pack_outer_multiselect_input = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt:
      "Synthesize A and B as one unit over model decision ND twin pack",
  };

  const pack_outer_decision_pack = {
    decision: pack_outer_decision_input,
    twin_search_pack: pack_outer_twin_search_pack,
  };

  const pack_outer_multi_pack = {
    multiselect: pack_outer_multiselect_input,
    decision_pack: pack_outer_decision_pack,
  };

  const pack_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent scaling laws body</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const pack_outer_draft_pack = {
    draft_gate: pack_outer_draft_gate,
    multi_pack: pack_outer_multi_pack,
  };

  const pack_outer_mo = {
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
    brief_dispatch_ready: true,
    stage: "unattended_pack" as const,
  };

  const pack_outer_mo_pack = {
    mo: pack_outer_mo,
    draft_pack: pack_outer_draft_pack,
  };

  const pack_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const pack_outer_fullscreen_pack = {
    fullscreen: pack_outer_fullscreen,
    mo_pack: pack_outer_mo_pack,
  };

  const pack_outer_write = {
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
        questions: [] as string[],
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

  const pack_outer_write_pack = {
    write: pack_outer_write,
    fullscreen_pack: pack_outer_fullscreen_pack,
  };

  const pack_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1",
  };

  const pack_outer_presentation = {
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

  const pack_outer_twin_presentation_pack = {
    twin: pack_outer_twin,
    presentation: pack_outer_presentation,
    write_pack: pack_outer_write_pack,
  };

  const pack_outer_weekly_learn = {
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

  const pack_outer_weekly_pack = {
    weekly_learn: pack_outer_weekly_learn,
    twin_presentation_pack: pack_outer_twin_presentation_pack,
  };

  const pack_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.85 as number | null,
    quality_floor: 0.7,
    would_exceed: false as boolean | null,
  };

  const pack_outer_source_pack = {
    sources: pack_outer_sources,
    weekly_pack: pack_outer_weekly_pack,
  };

  const pack_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const pack_outer_nd_pack = {
    nd_shadow: pack_outer_nd_shadow,
    source_pack: pack_outer_source_pack,
  };

  const pack_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const pack_outer_competition_pack = {
    competition: pack_outer_competition,
    nd_pack: pack_outer_nd_pack,
  };
  (outer_settings_pack as { competition_pack?: unknown }).competition_pack = pack_outer_competition_pack;
  (outer_market_pack as { competition_pack?: unknown }).competition_pack = pack_outer_competition_pack;


  const pack_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-html",
    purchase_ack: false,
    port_requested: true,
  };


  const pack_outer_settings = {
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
  const pack_outer_mo_for_market = {
    mo: pack_outer_mo,
    settings_pack: { settings: pack_outer_settings, competition_pack: pack_outer_competition_pack },
  };
  (outer_market_pack as { mo_pack?: unknown }).mo_pack = pack_outer_mo_for_market;
  const pack_outer_market_pack = {
    market: pack_outer_market,
    mo_pack: pack_outer_mo_for_market,
    competition_pack: pack_outer_competition_pack,
  };

  const pack_outer_settings_pack = {
    settings: pack_outer_settings,
    market_pack: pack_outer_market_pack,
    competition_pack: pack_outer_competition_pack,
  };

  const pack_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-html-ready",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const html_native_pack = {
    html_view: pack_outer_html_view,
    market_pack: pack_outer_market_pack,
    settings_pack: pack_outer_settings_pack,
  };

  const outer_model_decision_pack = {
    decision: pack_outer_decision_input,
    html_native_pack,
  };

  const pack_outer_twin_note_input = {
    parent_asset_id: "book-1",
    source_excerpt: "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    existing_twin_asset_id: "twin-book-1" as string | null,
    focus_questions: [
      "Where does scaling break under distribution shift?",
    ] as string[] | null,
  };

  const pack_outer_twin_search_for_note = {
    search_query: "scaling noise",
    twin_records: twin_search_records,
    model_decision_pack: outer_model_decision_pack,
  };

  const pack_outer_mo_price = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 25 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity(default 1)
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const pack_outer_twin_pack = {
    twin: pack_outer_twin_note_input,
    twin_search_pack: pack_outer_twin_search_for_note,
  };

  const residual_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Scaling Laws parent body</p>",
    sources: [
      {
        instance_id: "float-1",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws under noise",
        findings: ["evidence A holds under noise"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_mo_pack = {
    mo: pack_outer_mo_price,
    twin_pack: pack_outer_twin_pack,
  };

  const residual_highlight_surface = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    would_exceed: false as boolean | null,
    surface_action: "spawn_only" as const,
    source_families: ["arxiv" as const],
    twin_findings: [
      {
        source_id: "extra-1",
        body: "claim A supported under noise",
        kind: "insight" as const,
      },
    ],
    mark_for_prompt_context: true,
  };

  const residual_draft_pack = {
    draft_gate: residual_draft_gate,
    mo_pack: residual_mo_pack,
  };

  const residual_cf_floating_dr_pack = {
    highlight_surface: residual_highlight_surface,
    draft_pack: residual_draft_pack,
  };

  const residual_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_floating_dr_pack = {
    highlight_surface: residual_highlight_surface,
    draft_pack: residual_draft_pack,
  };

  const residual_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const residual_ms_floating_pack = {
    highlight_launch: {
      parent_asset_id: "book-1",
      highlight: "scaling laws under noise",
      gated: false,
      preferred_view_mode: "floating" as const,
      would_exceed: false as boolean | null,
      selected_model_id: "gpt-5.5",
      source_families: ["arxiv", "substack"] as (
        | "arxiv"
        | "substack"
        | "openalex"
        | "web"
        | "custom"
      )[],
    },
    record_pack: {
      session_id: "sess-1",
      items: [
        {
          record_id: "r1",
          kind: "insight" as const,
          text: "scaling holds under noise in compute-optimal regimes",
          asset_id: "book-1",
          weight: 0.9,
        },
        {
          record_id: "r2",
          kind: "question" as const,
          text: "Where does scaling break under distribution shift?",
          asset_id: "book-1",
          weight: 0.7,
        },
      ],
      decision_pack: pack_outer_decision_pack,
    },
  };

  const residual_collective_pack = {
    multiselect: residual_multiselect,
    floating_pack: residual_ms_floating_pack,
    floating_dr_pack: residual_floating_dr_pack,
  };

  const residual_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_fullscreen_pack = {
    fullscreen: residual_fullscreen,
    draft_pack: { draft_gate: residual_draft_gate, collective_pack: residual_collective_pack },
    collective_pack: residual_collective_pack,
  };

  const residual_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_write_pack = {
    write: residual_write,
    fullscreen_pack: residual_fullscreen_pack,
  };


  const residual_weekly_learn = {
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

  const residual_source_pack = {
    sources: residual_sources,
    write_pack: residual_write_pack,
  };

  const residual_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_presentation = {
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

  const residual_weekly_pack = {
    weekly_learn: residual_weekly_learn,
    source_pack: residual_source_pack,
  };

  const residual_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_twin_presentation = {
    twin: residual_twin,
    presentation: residual_presentation,
    weekly_pack: residual_weekly_pack,
  };

  const residual_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_nd_pack = {
    nd_shadow: residual_nd_shadow,
    twin_presentation: residual_twin_presentation,
  };

  const residual_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    ],
    decision_models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_competition_pack = {
    competition: residual_competition,
    nd_pack: residual_nd_pack,
  };

  const residual_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_settings_pack = {
    settings: residual_settings,
    competition_pack: residual_competition_pack,
  };

  const residual_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  // Outer pack for marketplace residual (avoid residual_mo_pack name collision with nest fixtures)
  const residual_outer_mo_pack = {
    mo: residual_mo,
    settings_pack: residual_settings_pack,
  };

  const residual_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_outer_market_pack = {
    market: residual_market,
    mo_pack: residual_outer_mo_pack,
  };

  const residual_twin_records = [
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

  const residual_outer_html_pack = {
    html_view: residual_html_view,
    market_pack: residual_outer_market_pack,
  };

  const residual_decision = {
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
    daily_cap_usd: 100 as number | null,
    spent_usd: 40 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: residual_twin_records,
    html_pack: residual_outer_html_pack,
  };

  const residual_record_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.7,
    },
  ];

  const residual_outer_decision_pack = {
    decision: residual_decision,
    twin_search_pack: residual_outer_twin_search_pack,
  };

  const residual_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_outer_record_pack = {
    session_id: "sess-1",
    items: residual_record_items,
    decision_pack: residual_outer_decision_pack,
  };

  const residual_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_outer_floating_pack = {
    highlight_launch: residual_highlight_launch,
    record_pack: residual_outer_record_pack,
  };

  const residual_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_outer_collective_pack = {
    multiselect: residual_outer_multiselect,
    floating_pack: residual_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const residual_outer_draft_pack = {
    draft_gate: residual_outer_draft_gate,
    collective_pack: residual_outer_collective_pack,
  };

  const residual_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_outer_fullscreen_pack = {
    fullscreen: residual_outer_fullscreen,
    draft_pack: residual_outer_draft_pack,
    collective_pack: residual_outer_collective_pack,
  };

  const residual_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_outer_write_pack = {
    write: residual_outer_write,
    fullscreen_pack: residual_outer_fullscreen_pack,
  };

  const residual_outer_weekly_learn = {
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

  const residual_outer_source_pack = {
    sources: residual_outer_sources,
    write_pack: residual_outer_write_pack,
  };

  const residual_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_outer_presentation = {
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

  const residual_outer_weekly_pack = {
    weekly_learn: residual_outer_weekly_learn,
    source_pack: residual_outer_source_pack,
  };

  const residual_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_outer_twin_presentation = {
    twin: residual_outer_twin,
    presentation: residual_outer_presentation,
    weekly_pack: residual_outer_weekly_pack,
  };

  const residual_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_outer_nd_pack = {
    nd_shadow: residual_outer_nd_shadow,
    twin_presentation: residual_outer_twin_presentation,
  };

  const residual_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    ],
    decision_models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_outer_competition_pack = {
    competition: residual_outer_competition,
    nd_pack: residual_outer_nd_pack,
  };

  const residual_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_outer_settings_pack = {
    settings: residual_outer_settings,
    competition_pack: residual_outer_competition_pack,
  };

  const residual_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  // Outer pack for marketplace residual (avoid residual_outer_mo_pack nest fixture collision)
  const residual_marketplace_mo_pack = {
    mo: residual_outer_mo,
    settings_pack: residual_outer_settings_pack,
  };

  const residual_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_html_native_market_pack = {
    market: residual_outer_market,
    mo_pack: residual_marketplace_mo_pack,
  };

  const residual_search_outer_twin_records = [
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

  const residual_twin_search_html_pack = {
    html_view: residual_outer_html_view,
    market_pack: residual_html_native_market_pack,
  };

  const residual_model_outer_decision = {
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
    daily_cap_usd: 100 as number | null,
    spent_usd: 40 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_model_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: residual_search_outer_twin_records,
    html_pack: residual_twin_search_html_pack,
  };

  const residual_workstation_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.7,
    },
  ];

  const residual_workstation_outer_decision_pack = {
    decision: residual_model_outer_decision,
    twin_search_pack: residual_model_outer_twin_search_pack,
  };

  const residual_floating_dr_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_floating_dr_record_pack = {
    session_id: "sess-1",
    items: residual_workstation_outer_items,
    decision_pack: residual_workstation_outer_decision_pack,
  };

  const residual_collective_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_collective_outer_floating_pack = {
    highlight_launch: residual_floating_dr_highlight_launch,
    record_pack: residual_floating_dr_record_pack,
  };

  const residual_draft_outer_draft_gate = {
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
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_draft_outer_collective_pack = {
    multiselect: residual_collective_outer_multiselect,
    floating_pack: residual_collective_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_fullscreen_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const residual_fullscreen_outer_draft_pack = {
    draft_gate: residual_draft_outer_draft_gate,
    collective_pack: residual_draft_outer_collective_pack,
  };

  const residual_write_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_write_outer_fullscreen_pack = {
    fullscreen: residual_fullscreen_outer_fullscreen,
    draft_pack: residual_fullscreen_outer_draft_pack,
    collective_pack: residual_draft_outer_collective_pack,
  };

  const residual_src_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
        html_fragment: "<article>essay…</article>",
      },
    ],
    quality_overall: 0.85 as number | null,
    quality_floor: 0.7 as number | null,
    would_exceed: false as boolean | null,
  };

  const residual_src_outer_write_pack = {
    write: residual_write_outer_write,
    fullscreen_pack: residual_write_outer_fullscreen_pack,
  };

  const residual_bench_outer_weekly_learn = {
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

  const residual_bench_outer_source_pack = {
    sources: residual_src_outer_sources,
    write_pack: residual_src_outer_write_pack,
  };

  const residual_rtp_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rtp_outer_presentation = {
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

  const residual_rtp_outer_weekly_pack = {
    weekly_learn: residual_bench_outer_weekly_learn,
    source_pack: residual_bench_outer_source_pack,
  };

  const residual_nd_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_nd_outer_twin_presentation = {
    twin: residual_rtp_outer_twin,
    presentation: residual_rtp_outer_presentation,
    weekly_pack: residual_rtp_outer_weekly_pack,
  };

  const residual_comp_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_comp_outer_nd_pack = {
    nd_shadow: residual_nd_outer_nd_shadow,
    twin_presentation: residual_nd_outer_twin_presentation,
  };

  const residual_settings_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    ],
    decision_models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_settings_outer_competition_pack = {
    competition: residual_comp_outer_competition,
    nd_pack: residual_comp_outer_nd_pack,
  };

  const residual_mo_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo_outer_settings_pack = {
    settings: residual_settings_outer_settings,
    competition_pack: residual_settings_outer_competition_pack,
  };

  const residual_mkt_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mkt_outer_mo_pack = {
    mo: residual_mo_outer_mo,
    settings_pack: residual_mo_outer_settings_pack,
  };

  const residual_html_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_html_outer_market_pack = {
    market: residual_mkt_outer_market,
    mo_pack: residual_mkt_outer_mo_pack,
  };

  const residual_moi_outer_twin_records = [
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

  const residual_moi_outer_html_pack = {
    html_view: residual_html_outer_html_view,
    market_pack: residual_html_outer_market_pack,
  };

  const residual_moi_outer_decision = {
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
    daily_cap_usd: 100 as number | null,
    spent_usd: 40 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_moi_outer_decision_pack = {
    decision: residual_moi_outer_decision,
    twin_search_pack: {
      search_query: "scaling noise",
      twin_records: residual_moi_outer_twin_records,
      html_pack: residual_moi_outer_html_pack,
    },
  };

  const residual_moi_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_moi_outer_record_pack = {
    session_id: "sess-1",
    items: residual_moi_outer_items,
    decision_pack: residual_moi_outer_decision_pack,
  };

  const residual_moi_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_moi_outer_floating_pack = {
    highlight_launch: residual_moi_outer_highlight_launch,
    record_pack: residual_moi_outer_record_pack,
  };

  const residual_moi_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_moi_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_moi_outer_collective_pack = {
    multiselect: residual_moi_outer_multiselect,
    floating_pack: residual_moi_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_moi_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const residual_moi_outer_draft_pack = {
    draft_gate: residual_moi_outer_draft_gate,
    collective_pack: residual_moi_outer_collective_pack,
  };

    const residual_moi_outer_fullscreen_pack = {
    fullscreen: residual_moi_outer_fullscreen,
    draft_pack: residual_moi_outer_draft_pack,
    collective_pack: residual_moi_outer_collective_pack,
  };

  const residual_moi_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

  const residual_moi_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_moi_outer_write_pack = {
    write: residual_moi_outer_write,
    fullscreen_pack: residual_moi_outer_fullscreen_pack,
  };

  const residual_moi_outer_weekly_learn = {
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

  const residual_moi_outer_source_pack = {
    sources: residual_moi_outer_sources,
    write_pack: residual_moi_outer_write_pack,
  };

  const residual_moi_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_moi_outer_presentation = {
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

  const residual_moi_outer_weekly_pack = {
    weekly_learn: residual_moi_outer_weekly_learn,
    source_pack: residual_moi_outer_source_pack,
  };

  const residual_moi_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_moi_outer_twin_presentation = {
    twin: residual_moi_outer_twin,
    presentation: residual_moi_outer_presentation,
    weekly_pack: residual_moi_outer_weekly_pack,
  };

  const residual_moi_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_moi_outer_nd_pack = {
    nd_shadow: residual_moi_outer_nd_shadow,
    twin_presentation: residual_moi_outer_twin_presentation,
  };

  const residual_moi_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    ],
    decision_models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_moi_outer_competition_pack = {
    competition: residual_moi_outer_competition,
    nd_pack: residual_moi_outer_nd_pack,
  };

  const residual_moi_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_moi_outer_settings_pack = {
    settings: residual_moi_outer_settings,
    competition_pack: residual_moi_outer_competition_pack,
  };

  const residual_mk2_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mk2_outer_mo_pack = {
    mo: residual_moi_outer_mo,
    settings_pack: residual_moi_outer_settings_pack,
  };

  const residual_hn_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn_outer_market_pack = {
    market: residual_mk2_outer_market,
    mo_pack: residual_mk2_outer_mo_pack,
  };

  const residual_md_outer_twin_records = [
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

  const residual_md_outer_html_pack = {
    html_view: residual_hn_outer_html_view,
    market_pack: residual_hn_outer_market_pack,
  };

  const residual_md_outer_decision = {
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

  const residual_md_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: residual_md_outer_twin_records,
    html_pack: residual_md_outer_html_pack,
  };

  const residual_ws_outer_decision_pack = {
    decision: residual_md_outer_decision,
    twin_search_pack: residual_md_outer_twin_search_pack,
  };

  const residual_ws_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_fd_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws_outer_items,
    decision_pack: residual_ws_outer_decision_pack,
  };

  const residual_fd_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_cm_outer_floating_pack = {
    highlight_launch: residual_fd_outer_highlight_launch,
    record_pack: residual_fd_outer_record_pack,
  };

  const residual_cm_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_db_outer_collective_pack = {
    multiselect: residual_cm_outer_multiselect,
    floating_pack: residual_cm_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_db_outer_draft_gate = {
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


  const residual_fs_outer_draft_pack = {
    draft_gate: residual_db_outer_draft_gate,
    collective_pack: residual_db_outer_collective_pack,
  };

  const residual_fs_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false,
  };


    const residual_wt_outer_fullscreen_pack = {
    fullscreen: residual_fs_outer_fullscreen,
    draft_pack: residual_fs_outer_draft_pack,
    collective_pack: residual_db_outer_collective_pack,
  };

  const residual_wt_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };


  const residual_sa_outer_write_pack = {
    write: residual_wt_outer_write,
    fullscreen_pack: residual_wt_outer_fullscreen_pack,
  };

  const residual_sa_outer_sources = {
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
    would_exceed: false as boolean | null,
  };


  const residual_ab_outer_source_pack = {
    sources: residual_sa_outer_sources,
    write_pack: residual_sa_outer_write_pack,
  };

  const residual_ab_outer_weekly_learn = {
    week_id: "2026-W28",
    min_events_per_task: 2,
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
  };


  const residual_rt_outer_weekly_pack = {
    weekly_learn: residual_ab_outer_weekly_learn,
    source_pack: residual_ab_outer_source_pack,
  };

  const residual_rt_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt_outer_presentation = {
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


  const residual_nds_outer_twin_presentation = {
    twin: residual_rt_outer_twin,
    presentation: residual_rt_outer_presentation,
    weekly_pack: residual_rt_outer_weekly_pack,
  };

  const residual_nds_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };


  const residual_cd_outer_nd_pack = {
    nd_shadow: residual_nds_outer_nd_shadow,
    twin_presentation: residual_nds_outer_twin_presentation,
  };

  const residual_cd_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };


  const residual_sd_outer_competition_pack = {
    competition: residual_cd_outer_competition,
    nd_pack: residual_cd_outer_nd_pack,
  };

  const residual_sd_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };


  const residual_mo2_outer_settings_pack = {
    settings: residual_sd_outer_settings,
    competition_pack: residual_sd_outer_competition_pack,
  };

  const residual_mo2_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };


  const residual_mk3_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mk3_outer_mo_pack = {
    mo: residual_mo2_outer_mo,
    settings_pack: residual_mo2_outer_settings_pack,
  };


  const residual_hn2_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn2_outer_market_pack = {
    market: residual_mk3_outer_market,
    mo_pack: residual_mk3_outer_mo_pack,
  };


  const residual_ts_outer_twin_records = [
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

  const residual_ts_outer_html_pack = {
    html_view: residual_hn2_outer_html_view,
    market_pack: residual_hn2_outer_market_pack,
  };


  const residual_md2_outer_decision = {
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
  };

  const residual_md2_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: residual_ts_outer_twin_records,
    html_pack: residual_ts_outer_html_pack,
  };


  const residual_ws2_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_ws2_outer_decision_pack = {
    decision: residual_md2_outer_decision,
    twin_search_pack: residual_md2_outer_twin_search_pack,
  };


  const residual_fd2_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_fd2_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws2_outer_items,
    decision_pack: residual_ws2_outer_decision_pack,
  };


  const residual_cm2_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_cm2_outer_floating_pack = {
    highlight_launch: residual_fd2_outer_highlight_launch,
    record_pack: residual_fd2_outer_record_pack,
  };


  const residual_db2_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_db2_outer_collective_pack = {
    multiselect: residual_cm2_outer_multiselect,
    floating_pack: residual_cm2_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };


  const residual_fs2_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  };

  const residual_fs2_outer_draft_pack = {
    draft_gate: residual_db2_outer_draft_gate,
    collective_pack: residual_db2_outer_collective_pack,
  };


  const residual_wt2_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt2_outer_fullscreen_pack = {
    fullscreen: residual_fs2_outer_fullscreen,
    draft_pack: residual_fs2_outer_draft_pack,
    collective_pack: residual_db2_outer_collective_pack,
  };


  const residual_sa2_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa2_outer_write_pack = {
    write: residual_wt2_outer_write,
    fullscreen_pack: residual_wt2_outer_fullscreen_pack,
  };


  const residual_ab2_outer_weekly_learn = {
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

  const residual_ab2_outer_source_pack = {
    sources: residual_sa2_outer_sources,
    write_pack: residual_sa2_outer_write_pack,
  };


  const residual_rt2_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt2_outer_presentation = {
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

  const residual_rt2_outer_weekly_pack = {
    weekly_learn: residual_ab2_outer_weekly_learn,
    source_pack: residual_ab2_outer_source_pack,
  };

  const residual_nds2_outer_twin_presentation = {
    twin: residual_rt2_outer_twin,
    presentation: residual_rt2_outer_presentation,
    weekly_pack: residual_rt2_outer_weekly_pack,
  };

  const residual_nds2_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_cd2_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  }

  const residual_cd2_outer_nd_pack = {
    nd_shadow: residual_nds2_outer_nd_shadow,
    twin_presentation: residual_nds2_outer_twin_presentation,
  };

  const residual_sd2_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  }

  const residual_sd2_outer_competition_pack = {
    competition: residual_cd2_outer_competition,
    nd_pack: residual_cd2_outer_nd_pack,
  };

  const residual_mo3_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  }

  const residual_mo3_outer_settings_pack = {
    settings: residual_sd2_outer_settings,
    competition_pack: residual_sd2_outer_competition_pack,
  };

  const residual_mk4_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  }

  const residual_mk4_outer_mo_pack = {
    mo: residual_mo3_outer_mo,
    settings_pack: residual_mo3_outer_settings_pack,
  };

  const residual_hn3_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  }

  const residual_hn3_outer_market_pack = {
    market: residual_mk4_outer_market,
    mo_pack: residual_mk4_outer_mo_pack,
  };

  const residual_ts2_outer_twin_records = [
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
  ]

  const residual_ts2_outer_html_pack = {
    html_view: residual_hn3_outer_html_view,
    market_pack: residual_hn3_outer_market_pack,
  };

  const residual_md3_outer_decision = {
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
  }

  const residual_md3_outer_twin_search_pack = {
    twin_records: residual_ts2_outer_twin_records,
    search_query: "scaling laws noise",
    html_pack: residual_ts2_outer_html_pack,
  };

  const residual_ws3_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ]

  const residual_ws3_outer_decision_pack = {
    decision: residual_md3_outer_decision,
    twin_search_pack: residual_md3_outer_twin_search_pack,
  };

  const residual_fd3_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  }

  const residual_fd3_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws3_outer_items,
    decision_pack: residual_ws3_outer_decision_pack,
  };

  const residual_cm3_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  }

  const residual_cm3_outer_floating_pack = {
    highlight_launch: residual_fd3_outer_highlight_launch,
    record_pack: residual_fd3_outer_record_pack,
  };

  const residual_db3_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  }

  const residual_db3_outer_collective_pack = {
    multiselect: residual_cm3_outer_multiselect,
    floating_pack: residual_cm3_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_fs3_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "Scaling laws claim from page 12",
    prompt: "What evidence supports this?",
    gated: false as boolean | null,
  }

  const residual_fs3_outer_draft_pack = {
    draft_gate: residual_db3_outer_draft_gate,
    collective_pack: residual_db3_outer_collective_pack,
  };

  const residual_wt3_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  }

    const residual_wt3_outer_fullscreen_pack = {
    fullscreen: residual_fs3_outer_fullscreen,
    draft_pack: residual_fs3_outer_draft_pack,
    collective_pack: residual_db3_outer_collective_pack,
  };

  const residual_sa3_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  }

  const residual_sa3_outer_write_pack = {
    write: residual_wt3_outer_write,
    fullscreen_pack: residual_wt3_outer_fullscreen_pack,
  };


  const residual_ab3_outer_weekly_learn = {
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

  const residual_ab3_outer_source_pack = {
    sources: residual_sa3_outer_sources,
    write_pack: residual_sa3_outer_write_pack,
  };


  const residual_rt3_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt3_outer_presentation = {
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

  const residual_rt3_outer_weekly_pack = {
    weekly_learn: residual_ab3_outer_weekly_learn,
    source_pack: residual_ab3_outer_source_pack,
  };


  const residual_nds3_outer_twin_presentation = {
    twin: residual_rt3_outer_twin,
    presentation: residual_rt3_outer_presentation,
    weekly_pack: residual_rt3_outer_weekly_pack,
  };

  const residual_nds3_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };


  const residual_cd3_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_cd3_outer_nd_pack = {
    nd_shadow: residual_nds3_outer_nd_shadow,
    twin_presentation: residual_nds3_outer_twin_presentation,
  };


  const residual_sd3_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  }

  const residual_sd3_outer_competition_pack = {
    competition: residual_cd3_outer_competition,
    nd_pack: residual_cd3_outer_nd_pack,
  };


  const residual_mo4_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo4_outer_settings_pack = {
    settings: residual_sd3_outer_settings,
    competition_pack: residual_sd3_outer_competition_pack,
  };


  const residual_mk5_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mk5_outer_mo_pack = {
    mo: residual_mo4_outer_mo,
    settings_pack: residual_mo4_outer_settings_pack,
  };


  const residual_hn4_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn4_outer_market_pack = {
    market: residual_mk5_outer_market,
    mo_pack: residual_mk5_outer_mo_pack,
  };


  const residual_ts3_outer_twin_records = [
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

  const residual_ts3_outer_html_pack = {
    html_view: residual_hn4_outer_html_view,
    market_pack: residual_hn4_outer_market_pack,
  };


  const residual_md4_outer_decision = {
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
  };

  const residual_md4_outer_twin_search_pack = {
    twin_records: residual_ts3_outer_twin_records,
    search_query: "scaling laws noise",
    html_pack: residual_ts3_outer_html_pack,
  };


  const residual_ws4_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_ws4_outer_decision_pack = {
    decision: residual_md4_outer_decision,
    twin_search_pack: residual_md4_outer_twin_search_pack,
  };


  const residual_fd4_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_fd4_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws4_outer_items,
    decision_pack: residual_ws4_outer_decision_pack,
  };


  const residual_cm4_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_cm4_outer_floating_pack = {
    highlight_launch: residual_fd4_outer_highlight_launch,
    record_pack: residual_fd4_outer_record_pack,
  };


  const residual_db4_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_db4_outer_collective_pack = {
    multiselect: residual_cm4_outer_multiselect,
    floating_pack: residual_cm4_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };


  const residual_fs4_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_fs4_outer_draft_pack = {
    draft_gate: residual_db4_outer_draft_gate,
    collective_pack: residual_db4_outer_collective_pack,
  };


  const residual_wt4_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt4_outer_fullscreen_pack = {
    fullscreen: residual_fs4_outer_fullscreen,
    draft_pack: residual_fs4_outer_draft_pack,
    collective_pack: residual_db4_outer_collective_pack,
  };


  const residual_sa4_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa4_outer_write_pack = {
    write: residual_wt4_outer_write,
    fullscreen_pack: residual_wt4_outer_fullscreen_pack,
  };


  const residual_ab4_outer_weekly_learn = {
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

  const residual_ab4_outer_source_pack = {
    sources: residual_sa4_outer_sources,
    write_pack: residual_sa4_outer_write_pack,
  };


  const residual_rt4_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt4_outer_presentation = {
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

  const residual_rt4_outer_weekly_pack = {
    weekly_learn: residual_ab4_outer_weekly_learn,
    source_pack: residual_ab4_outer_source_pack,
  };


  const residual_nds4_outer_twin_presentation = {
    twin: residual_rt4_outer_twin,
    presentation: residual_rt4_outer_presentation,
    weekly_pack: residual_rt4_outer_weekly_pack,
  };

  const residual_nds4_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };


  const residual_cd4_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_cd4_outer_nd_pack = {
    nd_shadow: residual_nds4_outer_nd_shadow,
    twin_presentation: residual_nds4_outer_twin_presentation,
  };


  const residual_sd4_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_sd4_outer_competition_pack = {
    competition: residual_cd4_outer_competition,
    nd_pack: residual_cd4_outer_nd_pack,
  };

  const residual_mo5_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo5_outer_settings_pack = {
    settings: residual_sd4_outer_settings,
    competition_pack: residual_sd4_outer_competition_pack,
  };


  const residual_mk6_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mk6_outer_mo_pack = {
    mo: residual_mo5_outer_mo,
    settings_pack: residual_mo5_outer_settings_pack,
  };

  const residual_hn5_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn5_outer_market_pack = {
    market: residual_mk6_outer_market,
    mo_pack: residual_mk6_outer_mo_pack,
  };

  const residual_ts4_outer_twin_records = [
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

  const residual_ts4_outer_html_pack = {
    html_view: residual_hn5_outer_html_view,
    market_pack: residual_hn5_outer_market_pack,
  };

  const residual_md5_outer_decision = {
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
  };

  const residual_md5_outer_twin_search_pack = {
    twin_records: residual_ts4_outer_twin_records,
    search_query: "scaling noise",
    html_pack: residual_ts4_outer_html_pack,
  };

  const residual_ws5_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_ws5_outer_decision_pack = {
    decision: residual_md5_outer_decision,
    twin_search_pack: residual_md5_outer_twin_search_pack,
  };

  const residual_fd5_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_fd5_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws5_outer_items,
    decision_pack: residual_ws5_outer_decision_pack,
  };

  const residual_cm5_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_cm5_outer_floating_pack = {
    highlight_launch: residual_fd5_outer_highlight_launch,
    record_pack: residual_fd5_outer_record_pack,
  };

  const residual_db5_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_db5_outer_collective_pack = {
    multiselect: residual_cm5_outer_multiselect,
    floating_pack: residual_cm5_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_fs5_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_fs5_outer_draft_pack = {
    draft_gate: residual_db5_outer_draft_gate,
    collective_pack: residual_db5_outer_collective_pack,
  };

  const residual_wt5_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt5_outer_fullscreen_pack = {
    fullscreen: residual_fs5_outer_fullscreen,
    draft_pack: residual_fs5_outer_draft_pack,
    collective_pack: residual_db5_outer_collective_pack,
  };

  const residual_sa5_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa5_outer_write_pack = {
    write: residual_wt5_outer_write,
    fullscreen_pack: residual_wt5_outer_fullscreen_pack,
  };

  const residual_ab5_outer_weekly_learn = {
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

  const residual_ab5_outer_source_pack = {
    sources: residual_sa5_outer_sources,
    write_pack: residual_sa5_outer_write_pack,
  };

  const residual_rt5_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt5_outer_presentation = {
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

  const residual_rt5_outer_weekly_pack = {
    weekly_learn: residual_ab5_outer_weekly_learn,
    source_pack: residual_ab5_outer_source_pack,
  };

  const residual_nds5_outer_twin_presentation = {
    twin: residual_rt5_outer_twin,
    presentation: residual_rt5_outer_presentation,
    weekly_pack: residual_rt5_outer_weekly_pack,
  };

  const residual_nds5_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };



  const residual_cd5_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_cd5_outer_nd_pack = {
    nd_shadow: residual_nds5_outer_nd_shadow,
    twin_presentation: residual_nds5_outer_twin_presentation,
  };


  const residual_sd5_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_sd5_outer_competition_pack = {
    competition: residual_cd5_outer_competition,
    nd_pack: residual_cd5_outer_nd_pack,
  };


  const residual_mo6_outer_mo_pre0 = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo6_outer_settings_pack_pre0 = {
    settings: residual_sd5_outer_settings,
    competition_pack: residual_sd5_outer_competition_pack,
  };


  const residual_mk8_outer_market_pre0 = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mk8_outer_mo_pack_pre0 = {
    mo: residual_mo6_outer_mo_pre0,
    settings_pack: residual_mo6_outer_settings_pack_pre0,
  };


  const residual_hn6_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn6_outer_market_pack = {
    market: residual_mk8_outer_market_pre0,
    mo_pack: residual_mk8_outer_mo_pack_pre0,
  };


  const residual_ts5_outer_twin_records = [
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

  const residual_ts5_outer_html_pack = {
    html_view: residual_hn6_outer_html_view,
    market_pack: residual_hn6_outer_market_pack,
  };


  const residual_md6_outer_decision = {
    models: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
  };

  const residual_md6_outer_twin_search_pack = {
    twin_records: residual_ts5_outer_twin_records,
    search_query: "scaling noise",
    html_pack: residual_ts5_outer_html_pack,
  };


  const residual_ws6_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_ws6_outer_decision_pack = {
    decision: residual_md6_outer_decision,
    twin_search_pack: residual_md6_outer_twin_search_pack,
  };


  const residual_fd6_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_fd6_outer_record_pack = {
    session_id: "sess-1",
    items: residual_ws6_outer_items,
    decision_pack: residual_ws6_outer_decision_pack,
  };


  const residual_cm6_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_cm6_outer_floating_pack = {
    highlight_launch: residual_fd6_outer_highlight_launch,
    record_pack: residual_fd6_outer_record_pack,
  };


  const residual_db6_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_db6_outer_collective_pack = {
    multiselect: residual_cm6_outer_multiselect,
    floating_pack: residual_cm6_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };


  const residual_fs6_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_fs6_outer_draft_pack = {
    draft_gate: residual_db6_outer_draft_gate,
    collective_pack: residual_db6_outer_collective_pack,
  };


  const residual_wt6_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt6_outer_fullscreen_pack = {
    fullscreen: residual_fs6_outer_fullscreen,
    draft_pack: residual_fs6_outer_draft_pack,
    collective_pack: residual_db6_outer_collective_pack,
  };


  const residual_sa6_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa6_outer_write_pack = {
    write: residual_wt6_outer_write,
    fullscreen_pack: residual_wt6_outer_fullscreen_pack,
  };


  const residual_ab6_outer_weekly_learn = {
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

  const residual_ab6_outer_source_pack = {
    sources: residual_sa6_outer_sources,
    write_pack: residual_sa6_outer_write_pack,
  };


  const residual_rt6_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt6_outer_presentation = {
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

  const residual_rt6_outer_weekly_pack = {
    weekly_learn: residual_ab6_outer_weekly_learn,
    source_pack: residual_ab6_outer_source_pack,
  };


  const residual_nds6_outer_twin_presentation = {
    twin: residual_rt6_outer_twin,
    presentation: residual_rt6_outer_presentation,
    weekly_pack: residual_rt6_outer_weekly_pack,
  };

  const residual_nds6_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };


  const residual_cd6_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_cd6_outer_nd_pack = {
    nd_shadow: residual_nds6_outer_nd_shadow,
    twin_presentation: residual_nds6_outer_twin_presentation,
  };


  const residual_sd6_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_sd6_outer_competition_pack = {
    competition: residual_cd6_outer_competition,
    nd_pack: residual_cd6_outer_nd_pack,
  };


  const residual_mo6_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo6_outer_settings_pack = {
    settings: residual_sd6_outer_settings,
    competition_pack: residual_sd6_outer_competition_pack,
  };



  /* --- grafted pure residual chain from c833 tip (self-contained) --- */
  const residual_graft_mo6_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    // ≥ recommended: work_minutes/60 * usd_per_hour * intensity
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_graft_mo6_outer_settings_pack = {
    settings: residual_sd6_outer_settings,
    competition_pack: residual_sd6_outer_competition_pack,
  };


  const residual_graft_mk8_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_graft_mk8_outer_mo_pack = {
    mo: residual_graft_mo6_outer_mo,
    settings_pack: residual_graft_mo6_outer_settings_pack,
  };


  const residual_graft_hn7_outer_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_graft_hn7_outer_market_pack = {
    market: residual_graft_mk8_outer_market,
    mo_pack: residual_graft_mk8_outer_mo_pack,
  };


  const residual_graft_ts7_outer_twin_records = [
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

  const residual_graft_ts7_outer_html_pack = {
    html_view: residual_graft_hn7_outer_html_view,
    market_pack: residual_graft_hn7_outer_market_pack,
  };


  const residual_graft_md7_outer_decision = {
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
      {
        model_id: "mimo-v2",
        tier: "workhorse",
        projected_cost_usd_high: 0.1,
      },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_graft_md7_outer_twin_search_pack = {
    search_query: "scaling noise",
    twin_records: residual_graft_ts7_outer_twin_records,
    html_pack: residual_graft_ts7_outer_html_pack,
  };


  const residual_graft_ws7_outer_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_graft_ws7_outer_decision_pack = {
    decision: residual_graft_md7_outer_decision,
    twin_search_pack: residual_graft_md7_outer_twin_search_pack,
  };


  const residual_graft_fd7_outer_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_graft_fd7_outer_record_pack = {
    session_id: "sess-1",
    items: residual_graft_ws7_outer_items,
    decision_pack: residual_graft_ws7_outer_decision_pack,
  };


  const residual_graft_cm7_outer_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_graft_cm7_outer_floating_pack = {
    highlight_launch: residual_graft_fd7_outer_highlight_launch,
    record_pack: residual_graft_fd7_outer_record_pack,
  };

const residual_graft_db7_outer_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_graft_db7_outer_collective_pack = {
    multiselect: residual_graft_cm7_outer_multiselect,
    floating_pack: residual_graft_cm7_outer_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };


  const residual_graft_fs7_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_graft_fs7_outer_draft_pack = {
    draft_gate: residual_graft_db7_outer_draft_gate,
    collective_pack: residual_graft_db7_outer_collective_pack,
  };

const residual_graft_wt7_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_graft_wt7_outer_fullscreen_pack = {
    fullscreen: residual_graft_fs7_outer_fullscreen,
    draft_pack: residual_graft_fs7_outer_draft_pack,
    collective_pack: residual_graft_db7_outer_collective_pack,
  };

const residual_graft_sa7_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_graft_sa7_outer_write_pack = {
    write: residual_graft_wt7_outer_write,
    fullscreen_pack: residual_graft_wt7_outer_fullscreen_pack,
  };

const residual_graft_ab7_outer_weekly_learn = {
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

  const residual_graft_ab7_outer_source_pack = {
    sources: residual_graft_sa7_outer_sources,
    write_pack: residual_graft_sa7_outer_write_pack,
  };

const residual_graft_rt7_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

const residual_graft_rt7_outer_presentation = {
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

  const residual_graft_rt7_outer_weekly_pack = {
    weekly_learn: residual_graft_ab7_outer_weekly_learn,
    source_pack: residual_graft_ab7_outer_source_pack,
  };

const residual_graft_nds7_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_graft_nds7_outer_twin_presentation = {
    twin: residual_graft_rt7_outer_twin,
    presentation: residual_graft_rt7_outer_presentation,
    weekly_pack: residual_graft_rt7_outer_weekly_pack,
  };

const residual_graft_cd7_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_graft_cd7_outer_nd_pack = {
    nd_shadow: residual_graft_nds7_outer_nd_shadow,
    twin_presentation: residual_graft_nds7_outer_twin_presentation,
  };

const residual_graft_sd7_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_graft_sd7_outer_competition_pack = {
    competition: residual_graft_cd7_outer_competition,
    nd_pack: residual_graft_cd7_outer_nd_pack,
  };

  const residual_graft_mo7_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_graft_mo7_outer_settings_pack = {
    settings: residual_graft_sd7_outer_settings,
    competition_pack: residual_graft_sd7_outer_competition_pack,
  };

  const residual_graft_mkt7_tip_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_graft_mkt7_tip_mo_pack = {
    mo: residual_graft_mo7_outer_mo,
    settings_pack: residual_graft_mo7_outer_settings_pack,
  };

  const residual_graft_hn8_tip_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_graft_hn8_tip_market_pack = {
    market: residual_graft_mkt7_tip_market,
    mo_pack: residual_graft_mkt7_tip_mo_pack,
  };

  const residual_graft_ts8_tip_twin_records = [
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

  const residual_graft_ts8_tip_html_pack = {
    html_view: residual_graft_hn8_tip_html_view,
    market_pack: residual_graft_hn8_tip_market_pack,
  };

  const residual_graft_md8_tip_decision = {
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
      {
        model_id: "mimo-v2",
        tier: "workhorse",
        projected_cost_usd_high: 0.1,
      },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_graft_md8_tip_twin_search_pack = {
    search_query: "scaling laws",
    twin_records: residual_graft_ts8_tip_twin_records,
    html_pack: residual_graft_ts8_tip_html_pack,
  };

  const residual_graft_ws8_tip_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_graft_ws8_tip_decision_pack = {
    decision: residual_graft_md8_tip_decision,
    twin_search_pack: residual_graft_md8_tip_twin_search_pack,
  };

  const residual_graft_fd8_tip_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_graft_fd8_tip_record_pack = {
    session_id: "sess-1",
    items: residual_graft_ws8_tip_items,
    decision_pack: residual_graft_ws8_tip_decision_pack,
  };

  const residual_graft_cm8_tip_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_graft_cm8_tip_floating_pack = {
    highlight_launch: residual_graft_fd8_tip_highlight_launch,
    record_pack: residual_graft_fd8_tip_record_pack,
  };

  const residual_graft_db8_tip_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_graft_db8_tip_collective_pack = {
    multiselect: residual_graft_cm8_tip_multiselect,
    floating_pack: residual_graft_cm8_tip_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };


  const residual_fs8_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_fs8_outer_draft_pack = {
    draft_gate: residual_graft_db8_tip_draft_gate,
    collective_pack: residual_graft_db8_tip_collective_pack,
  };


const residual_wt8_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt8_outer_fullscreen_pack = {
    fullscreen: residual_fs8_outer_fullscreen,
    draft_pack: residual_fs8_outer_draft_pack,
    collective_pack: residual_graft_db8_tip_collective_pack,
  };




  const residual_sa8_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa8_outer_write_pack = {
    write: residual_wt8_outer_write,
    fullscreen_pack: residual_wt8_outer_fullscreen_pack,
  };


const residual_ab8_outer_weekly_learn = {
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

  const residual_ab8_outer_source_pack = {
    sources: residual_sa8_outer_sources,
    write_pack: residual_sa8_outer_write_pack,
  };


const residual_rt8_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };
const residual_rt8_outer_presentation = {
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
  const residual_rt8_outer_weekly_pack = {
    weekly_learn: residual_ab8_outer_weekly_learn,
    source_pack: residual_ab8_outer_source_pack,
  };

const residual_nds8_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };
  const residual_nds8_outer_twin_presentation = {
    twin: residual_rt8_outer_twin,
    presentation: residual_rt8_outer_presentation,
    weekly_pack: residual_rt8_outer_weekly_pack,
  };

const residual_cd8_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };
  const residual_cd8_outer_nd_pack = {
    nd_shadow: residual_nds8_outer_nd_shadow,
    twin_presentation: residual_nds8_outer_twin_presentation,
  };

  const residual_sd8_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_sd8_outer_competition_pack = {
    competition: residual_cd8_outer_competition,
    nd_pack: residual_cd8_outer_nd_pack,
  };


  const residual_mo8_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_mo8_outer_settings_pack = {
    settings: residual_sd8_outer_settings,
    competition_pack: residual_sd8_outer_competition_pack,
  };


  const residual_mk8_outer_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mkt8_outer_mo_pack = {
    mo: residual_mo8_outer_mo,
    settings_pack: residual_mo8_outer_settings_pack,
  };


  const residual_mkt8_tip_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_mkt8_tip_mo_pack = {
    mo: residual_mo8_outer_mo,
    settings_pack: residual_mo8_outer_settings_pack,
  };



  const residual_hn9_tip_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };

  const residual_hn9_tip_market_pack = {
    market: residual_mkt8_tip_market,
    mo_pack: residual_mkt8_tip_mo_pack,
  };



  const residual_ts9_tip_twin_records = [
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

  const residual_ts9_tip_html_pack = {
    html_view: residual_hn9_tip_html_view,
    market_pack: residual_hn9_tip_market_pack,
  };



  const residual_md9_tip_decision = {
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
      {
        model_id: "mimo-v2",
        tier: "workhorse",
        projected_cost_usd_high: 0.1,
      },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_md9_tip_twin_search_pack = {
    search_query: "scaling laws under noise",
    twin_records: residual_ts9_tip_twin_records,
    html_pack: residual_ts9_tip_html_pack,
  };



// --- residual ×10 tip graft + residual_md10 ---
// --- residual ×10 tip graft + residual_ts10 ---
// --- residual ×10 tip graft + residual_hn10 ---
// --- residual ×9 tip graft + residual_mkt9 ---
// --- residual ×9 tip graft (mkt8→sd9) + residual_mo9 ---
    
  
            const residual_ws9_tip_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_ws9_tip_decision_pack = {
    decision: residual_md9_tip_decision,
    twin_search_pack: residual_md9_tip_twin_search_pack,
  };

  const residual_fd9_tip_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_fd9_tip_record_pack = {
    session_id: "sess-1",
    items: residual_ws9_tip_items,
    decision_pack: residual_ws9_tip_decision_pack,
  };

  const residual_cm9_tip_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_cm9_tip_floating_pack = {
    highlight_launch: residual_fd9_tip_highlight_launch,
    record_pack: residual_fd9_tip_record_pack,
  };

  const residual_db9_tip_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_db9_tip_collective_pack = {
    multiselect: residual_cm9_tip_multiselect,
    floating_pack: residual_cm9_tip_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_fs9_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_fs9_outer_draft_pack = {
    draft_gate: residual_db9_tip_draft_gate,
    collective_pack: residual_db9_tip_collective_pack,
  };


const residual_wt9_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_wt9_outer_fullscreen_pack = {
    fullscreen: residual_fs9_outer_fullscreen,
    draft_pack: residual_fs9_outer_draft_pack,
    collective_pack: residual_db9_tip_collective_pack,
  };




  const residual_sa9_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_sa9_outer_write_pack = {
    write: residual_wt9_outer_write,
    fullscreen_pack: residual_wt9_outer_fullscreen_pack,
  };


const residual_ab9_outer_weekly_learn = {
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

  const residual_ab9_outer_source_pack = {
    sources: residual_sa9_outer_sources,
    write_pack: residual_sa9_outer_write_pack,
  };

  const residual_rtx_fs9_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_rtx_fs9_outer_draft_pack = {
    draft_gate: residual_db9_tip_draft_gate,
    collective_pack: residual_db9_tip_collective_pack,
  };


const residual_rtx_wt9_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_rtx_wt9_outer_fullscreen_pack = {
    fullscreen: residual_rtx_fs9_outer_fullscreen,
    draft_pack: residual_rtx_fs9_outer_draft_pack,
    collective_pack: residual_db9_tip_collective_pack,
  };




  const residual_rtx_sa9_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_rtx_sa9_outer_write_pack = {
    write: residual_rtx_wt9_outer_write,
    fullscreen_pack: residual_rtx_wt9_outer_fullscreen_pack,
  };

  const residual_abx_fs9_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_abx_fs9_outer_draft_pack = {
    draft_gate: residual_db9_tip_draft_gate,
    collective_pack: residual_db9_tip_collective_pack,
  };


const residual_abx_wt9_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

    const residual_abx_wt9_outer_fullscreen_pack = {
    fullscreen: residual_abx_fs9_outer_fullscreen,
    draft_pack: residual_abx_fs9_outer_draft_pack,
    collective_pack: residual_db9_tip_collective_pack,
  };

const residual_abx_sa9_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_abx_sa9_outer_write_pack = {
    write: residual_abx_wt9_outer_write,
    fullscreen_pack: residual_abx_wt9_outer_fullscreen_pack,
  };

const residual_rtx_ab9_outer_weekly_learn = {
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

  const residual_rtx_ab9_outer_source_pack = {
    sources: residual_rtx_sa9_outer_sources,
    write_pack: residual_rtx_sa9_outer_write_pack,
  };

const residual_rt9_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };
const residual_rt9_outer_presentation = {
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
  const residual_rt9_outer_weekly_pack = {
    weekly_learn: residual_ab9_outer_weekly_learn,
    source_pack: residual_ab9_outer_source_pack,
  };


const residual_nds9_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };
  const residual_nds9_outer_twin_presentation = {
    twin: residual_rt9_outer_twin,
    presentation: residual_rt9_outer_presentation,
    weekly_pack: residual_rt9_outer_weekly_pack,
  };
const residual_cd9_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };
  const residual_cd9_outer_nd_pack = {
    nd_shadow: residual_nds9_outer_nd_shadow,
    twin_presentation: residual_nds9_outer_twin_presentation,
  };
const residual_sd9_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };
  const residual_sd9_outer_competition_pack = {
    competition: residual_cd9_outer_competition,
    nd_pack: residual_cd9_outer_nd_pack,
  };
const residual_mo9_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };
  const residual_mo9_outer_settings_pack = {
    settings: residual_sd9_outer_settings,
    competition_pack: residual_sd9_outer_competition_pack,
  };
const residual_mkt9_tip_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };
  const residual_mkt9_tip_mo_pack = {
    mo: residual_mo9_outer_mo,
    settings_pack: residual_mo9_outer_settings_pack,
  };
const residual_hn10_tip_html_view = {
    session_id: "sess-1",
    asset_id: "book-1",
    html_projection_sha: "sha-free-1",
    view_requested: true,
    twin_bound: true,
    twin_substrate_ready: true,
    claimed_format: "html" as const,
  };
  const residual_hn10_tip_market_pack = {
    market: residual_mkt9_tip_market,
    mo_pack: residual_mkt9_tip_mo_pack,
  };
const residual_ts10_tip_twin_records = [
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
  const residual_ts10_tip_html_pack = {
    html_view: residual_hn10_tip_html_view,
    market_pack: residual_hn10_tip_market_pack,
  };
  const residual_mo10_outer_mo = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_sd10_outer_settings = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
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
    models_for_bench: [
      { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
      { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
      { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 20 as number | null,
    spent_usd: 5 as number | null,
    projected_cost_usd_high: 0.5 as number | null,
    projected_cost_usd_low: 0.2 as number | null,
    existing_tasks: ["deep_research", "twin_notes"] as string[] | null,
  };

  const residual_cd10_outer_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_nds10_outer_nd_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_rt10_outer_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt10_outer_presentation = {
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

  const residual_ab10_outer_weekly_learn = {
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

  const residual_sa10_outer_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv" as const, "substack" as const],
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling laws",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on routing",
        url: "https://example.substack.com/p/routing",
      },
    ],
  };

  const residual_wt10_outer_write = {
    session_id: "sess-1",
    draft_id: "draft-1",
    parent_asset_id: "book-1",
    twin_slices: [
      {
        parent_asset_id: "book-1",
        insights: ["scaling claim holds in compute-optimal regimes"],
        questions: ["Where does it break?"],
      },
      {
        parent_asset_id: "book-1-twin-slice-2",
        insights: ["attention efficiency tradeoffs"],
        questions: [] as string[],
      },
    ],
    base_draft_html: "<p>Opening paragraph</p>" as string | null,
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
    extra_findings: ["operator synthesis note"] as string[] | null,
  };

  const residual_fs10_outer_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
  };

  const residual_db10_tip_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["finding-b1"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_cm10_tip_multiselect = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    members: [
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
    ],
    selected_instance_ids: ["inst-a", "inst-b"],
    pack_mode: "cohesive_prompt" as const,
    cohesive_prompt: "Synthesize A and B as one unit",
    extra_context: ["operator note"] as string[] | null,
  };

  const residual_fd10_tip_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as (
      | "arxiv"
      | "substack"
      | "openalex"
      | "web"
      | "custom"
    )[],
  };

  const residual_ws10_tip_items = [
    {
      record_id: "r1",
      kind: "insight" as const,
      text: "scaling holds under noise in compute-optimal regimes",
      asset_id: "book-1",
      weight: 0.9,
    },
    {
      record_id: "r2",
      kind: "question" as const,
      text: "Where does scaling break under distribution shift?",
      asset_id: "book-1",
      weight: 0.8,
    },
  ];

  const residual_graft_md10_tip_decision = {
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
      {
        model_id: "mimo-v2",
        tier: "workhorse",
        projected_cost_usd_high: 0.1,
      },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_graft_ts10_tip_twin_records = [
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

  const residual_graft_ts10_tip_html_pack = {
    html_view: residual_hn10_tip_html_view,
    market_pack: residual_hn10_tip_market_pack,
  };

  const residual_mkt10_tip_market = {
    title: "Scaling Laws Book",
    account_id: "acct-1",
    free_copy_available: true as boolean | null,
    free_html_projection_sha: "sha-free-1",
    purchase_ack: false,
    port_requested: true,
  };

  const residual_graft_md10_tip_twin_search_pack = {
    search_query: "scaling laws",
    twin_records: residual_graft_ts10_tip_twin_records,
    html_pack: residual_graft_ts10_tip_html_pack,
  };

  const residual_ws10_tip_decision_pack = {
    decision: residual_graft_md10_tip_decision,
    twin_search_pack: residual_graft_md10_tip_twin_search_pack,
  };

  const residual_fd10_tip_record_pack = {
    session_id: "sess-1",
    items: residual_ws10_tip_items,
    decision_pack: residual_ws10_tip_decision_pack,
  };

  const residual_cm10_tip_floating_pack = {
    highlight_launch: residual_fd10_tip_highlight_launch,
    record_pack: residual_fd10_tip_record_pack,
  };

  const residual_db10_tip_collective_pack = {
    multiselect: residual_cm10_tip_multiselect,
    floating_pack: residual_cm10_tip_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };

  const residual_fs10_outer_draft_pack = {
    draft_gate: residual_db10_tip_draft_gate,
    collective_pack: residual_db10_tip_collective_pack,
  };

    const residual_wt10_outer_fullscreen_pack = {
    fullscreen: residual_fs10_outer_fullscreen,
    draft_pack: residual_fs10_outer_draft_pack,
    collective_pack: residual_db10_tip_collective_pack,
  };

  const residual_sa10_outer_write_pack = {
    write: residual_wt10_outer_write,
    fullscreen_pack: residual_wt10_outer_fullscreen_pack,
  };

  const residual_ab10_outer_source_pack = {
    sources: residual_sa10_outer_sources,
    write_pack: residual_sa10_outer_write_pack,
  };

  const residual_rt10_outer_weekly_pack = {
    weekly_learn: residual_ab10_outer_weekly_learn,
    source_pack: residual_ab10_outer_source_pack,
  };

  const residual_nds10_outer_twin_presentation = {
    twin: residual_rt10_outer_twin,
    presentation: residual_rt10_outer_presentation,
    weekly_pack: residual_rt10_outer_weekly_pack,
  };

  const residual_cd10_outer_nd_pack = {
    nd_shadow: residual_nds10_outer_nd_shadow,
    twin_presentation: residual_nds10_outer_twin_presentation,
  };

  const residual_sd10_outer_competition_pack = {
    competition: residual_cd10_outer_competition,
    nd_pack: residual_cd10_outer_nd_pack,
  };

  const residual_mo10_outer_settings_pack = {
    settings: residual_sd10_outer_settings,
    competition_pack: residual_sd10_outer_competition_pack,
  };

  const residual_mkt10_tip_mo_pack = {
    mo: residual_mo10_outer_mo,
    settings_pack: residual_mo10_outer_settings_pack,
  };

  // residual_md11 tip graft: MoWeekly×11 moniker needs residual_mkt11 mo_pack depth
  // through mo11→sd11→cd11→… (nest lag residual_mkt10 mo_pack inside chain avoids TDZ)
  const residual_md10_tip_decision = {
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
      {
        model_id: "mimo-v2",
        tier: "workhorse",
        projected_cost_usd_high: 0.1,
      },
    ],
    selected_model_id: "gpt-5.5",
    daily_cap_usd: 50 as number | null,
    spent_usd: 10 as number | null,
    projected_cost_usd_high: 2 as number | null,
    projected_cost_usd_low: 1 as number | null,
    focus_task: "deep_research",
    pending_add_model_ids: ["mimo-v2"] as string[] | null,
  };

  const residual_ws11_tip_decision_pack = {
    decision: residual_md10_tip_decision,
    twin_search_pack: {
      search_query: "scaling laws",
      twin_records: residual_ts10_tip_twin_records,
      html_pack: {
        html_view: residual_hn10_tip_html_view,
        market_pack: {
          market: residual_mkt10_tip_market,
          mo_pack: residual_mkt10_tip_mo_pack,
        },
      },
    },
  };
  residual_ms_floating_pack.record_pack.decision_pack = residual_ws11_tip_decision_pack;

  const residual_fd11_tip_record_pack = {
    session_id: "sess-1",
    items: residual_ws10_tip_items,
    decision_pack: residual_ws11_tip_decision_pack,
  };
  const residual_cm11_tip_floating_pack = {
    highlight_launch: residual_fd10_tip_highlight_launch,
    record_pack: residual_fd11_tip_record_pack,
  };
  const residual_db11_tip_collective_pack = {
    multiselect: residual_cm10_tip_multiselect,
    floating_pack: residual_cm11_tip_floating_pack,
  floating_dr_pack: residual_cf_floating_dr_pack,
  };
  const residual_fs11_outer_draft_pack = {
    draft_gate: residual_db10_tip_draft_gate,
    collective_pack: residual_db11_tip_collective_pack,
  };
    const residual_wt11_outer_fullscreen_pack = {
    fullscreen: residual_fs10_outer_fullscreen,
    draft_pack: residual_fs11_outer_draft_pack,
    collective_pack: residual_db11_tip_collective_pack,
  };
  const residual_sa11_outer_write_pack = {
    write: residual_wt10_outer_write,
    fullscreen_pack: residual_wt11_outer_fullscreen_pack,
  };
  const residual_ab11_outer_source_pack = {
    sources: residual_sa10_outer_sources,
    write_pack: residual_sa11_outer_write_pack,
  };
  const residual_rt11_outer_weekly_pack = {
    weekly_learn: residual_ab10_outer_weekly_learn,
    source_pack: residual_ab11_outer_source_pack,
  };
  const residual_nds11_outer_twin_presentation = {
    twin: residual_rt10_outer_twin,
    presentation: residual_rt10_outer_presentation,
    weekly_pack: residual_rt11_outer_weekly_pack,
  };
  const residual_cd11_outer_nd_pack = {
    nd_shadow: residual_nds10_outer_nd_shadow,
    twin_presentation: residual_nds11_outer_twin_presentation,
  };
  const residual_sd11_outer_competition_pack = {
    competition: residual_cd10_outer_competition,
    nd_pack: residual_cd11_outer_nd_pack,
  };
  const residual_mo11_outer_settings_pack = {
    settings: residual_sd10_outer_settings,
    competition_pack: residual_sd11_outer_competition_pack,
  };
  const residual_mkt11_tip_mo_pack = {
    mo: residual_mo10_outer_mo,
    settings_pack: residual_mo11_outer_settings_pack,
  };
  // actual market_pack for twin-search residual over HTML-native MoWeekly=11 moniker
  const residual_hn11_tip_market_pack = {
    market: residual_mkt10_tip_market,
    mo_pack: residual_mkt11_tip_mo_pack,
  };

  const residual_ts11_tip_html_pack = {
    html_view: residual_hn10_tip_html_view,
    market_pack: residual_hn11_tip_market_pack,
  };

  const residual_md11_tip_twin_search_pack = {
    search_query: "scaling laws",
    twin_records: residual_ts10_tip_twin_records,
    html_pack: residual_ts11_tip_html_pack,
  };

  const residual_md10_tip_twin_search_pack = {
    search_query: "scaling laws",
    twin_records: residual_ts10_tip_twin_records,
    html_pack: residual_ts10_tip_html_pack,
  };

  const residual_ws_items = [
        { record_id: "r-ws-1", kind: "insight" as const, text: "Workstation residual records scaling laws under noise" },
        { record_id: "r-ws-2", kind: "question" as const, text: "What residual gaps remain in the research loop?" },
      ];

  const residual_ws_decision_pack = {
    decision: residual_md10_tip_decision,
    twin_search_pack: residual_md11_tip_twin_search_pack,
  };

  const residual_fdr_record_pack = {
    session_id: "sess-1",
    items: residual_ws_items,
    decision_pack: residual_ws_decision_pack,
  };

  const residual_fdr_highlight_launch = {
    parent_asset_id: "book-1",
    highlight: "scaling laws claim under noise",
    gated: false,
    preferred_view_mode: "floating" as const,
    would_exceed: false as boolean | null,
    selected_model_id: "gpt-5.5",
    source_families: ["arxiv", "substack"] as const,
  };

  const residual_col_floating_pack = {
    highlight_launch: residual_fdr_highlight_launch,
    record_pack: residual_fdr_record_pack,
  };

  const residual_col_multiselect = {
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
    cohesive_prompt: "Synthesize A and B as one unit over floating DR residual",
  };

  const residual_dbm_collective_pack = {
    multiselect: residual_col_multiselect,
    floating_pack: residual_col_floating_pack,
  };

  const residual_dbm_draft_gate = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    parent_excerpt: "<p>Parent body on scaling laws</p>",
    sources: [
      {
        instance_id: "inst-a",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "scaling laws claim",
        findings: ["evidence A"],
      },
      {
        instance_id: "inst-b",
        parent_asset_id: "book-1",
        status: "completed" as const,
        highlight: "counter-evidence",
        findings: ["evidence B"],
      },
    ],
    stage: "draft_only" as const,
  };

  const residual_fs_draft_pack = {
    draft_gate: residual_dbm_draft_gate,
    collective_pack: residual_dbm_collective_pack,
  };

  const residual_fs_fullscreen = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    highlight: "scaling laws claim under noise",
    gated: false,
    prompt: "Open this floating DR fullscreen for deep read",
  };

  const residual_wt_fullscreen_pack = {
    fullscreen: residual_fs_fullscreen,
    draft_pack: residual_fs_draft_pack,
  };

  const residual_wt_write = {
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

  const residual_sa_write_pack = {
    write: residual_wt_write,
    fullscreen_pack: residual_wt_fullscreen_pack,
  };

  const residual_sa_sources = {
    session_id: "sess-1",
    parent_asset_id: "book-1",
    requested_families: ["arxiv", "substack"] as const,
    sources: [
      {
        source_id: "s1",
        family: "arxiv" as const,
        title: "Scaling Laws under Noise",
        external_id: "arxiv:2301.00001",
        html_fragment: "<article>abstract…</article>",
      },
      {
        source_id: "s2",
        family: "substack" as const,
        title: "Essay on evals",
        url: "https://example.substack.com/p/evals",
        html_fragment: "<article>substack body…</article>",
      },
    ],
  };

  const residual_ab_weekly_learn = {
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

  const residual_ab_source_pack = {
    sources: residual_sa_sources,
    write_pack: residual_sa_write_pack,
  };

  const residual_rt_twin = {
    parent_asset_id: "book-1",
    source_excerpt:
      "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
    focus_questions: ["Where does it break?", "What residual gaps?"],
    existing_twin_asset_id: "twin-book-1" as string | null,
  };

  const residual_rt_presentation = {
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

  const residual_rt_weekly_pack = {
    weekly_learn: residual_ab_weekly_learn,
    source_pack: residual_ab_source_pack,
  };

  const residual_nds_shadow = {
    selected_model_id: "gpt-5.5",
    nd_recommended_model_id: "claude-opus",
    kill_switch_on: true,
    confidence: 0.72,
    task: "deep_research",
    inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
  };

  const residual_nds_twin_presentation = {
    twin: residual_rt_twin,
    presentation: residual_rt_presentation,
    weekly_pack: residual_rt_weekly_pack,
  };

  const residual_cd_competition = {
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
    requested_families: ["arxiv", "substack"] as ("arxiv" | "substack")[],
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
    quality_overall: 0.8 as number | null,
    quality_floor: 0.5,
    would_exceed: false as boolean | null,
  };

  const residual_cd_nd_pack = {
    nd_shadow: residual_nds_shadow,
    twin_presentation: residual_nds_twin_presentation,
  };

  const residual_market_tip = {
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
  };

  const residual_mo_tip = {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Map scaling literature" },
      { goal_id: "g2", title: "Synthesize open problems" },
    ],
    usd_per_hour: 30 as number | null,
    approved_ceiling_usd: 500 as number | null,
    price_ceiling_ack: true,
    unattended_ack: true,
    spend_consent: true,
    stage: "unattended_pack" as const,
  };

  const residual_settings_tip = {
    models: [
      { model_id: "gpt-5.5", provider: "openai" },
      { model_id: "grok-4.5", provider: "xai" },
    ],
    pending_add_model_ids: ["mimo-v2"],
    action: "preview" as const,
    week_id: "2026-W28",
    focus_task: "deep_research",
    events: [
      { event_id: "e1", task: "deep_research", model_id: "gpt-5.5", outcome: "worked" as const, score: 0.9 },
      { event_id: "e2", task: "deep_research", model_id: "gpt-5.5", outcome: "worked" as const, score: 0.85 },
      { event_id: "e3", task: "deep_research", model_id: "mimo-v2", outcome: "failed" as const, score: 0.2 },
      { event_id: "e4", task: "deep_research", model_id: "mimo-v2", outcome: "failed" as const, score: 0.3 },
      { event_id: "e5", task: "twin_notes", model_id: "grok-4.5", outcome: "worked" as const, score: 0.8 },
      { event_id: "e6", task: "twin_notes", model_id: "grok-4.5", outcome: "worked" as const, score: 0.75 },
    ],
    daily_cap_usd: 25,
    spent_usd: 4,
    selected_model_id: "gpt-5.5",
    projected_cost_usd_high: 2,
    projected_cost_usd_low: 1,
  };

  const residual_mo_pack_tip = {
    mo: residual_mo_tip,
    settings_pack: {
      settings: residual_settings_tip,
      competition_pack: {
        competition: residual_cd_competition,
        nd_pack: residual_cd_nd_pack,
      },
    },
  };

  it("marketplace free + MO residual pack ready", () => {
    const c = composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack({
      market: residual_market_tip,
      mo_pack: residual_mo_pack_tip,
      operator_ack: true,
    });
    expect(c.pack_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
    expect(formatMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackSummary(c)).toMatch(/REJECT|pack_ready=true|purchase_executed=false/);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack({
      market: residual_market_tip,
      mo_pack: residual_mo_pack_tip,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.purchase_executed).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("purchase path remains free-only honesty", () => {
    const c = composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack({
      market: { ...residual_market_tip, free_copy_available: true, purchase_ack: false },
      mo_pack: residual_mo_pack_tip,
      operator_ack: true,
    });
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.production_router_verdict).toBe("REJECT");
  });

  it("production router remains REJECT", () => {
    const c = composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack({
      market: residual_market_tip,
      mo_pack: residual_mo_pack_tip,
      operator_ack: true,
    });
    expect(c.production_router_verdict).toBe("REJECT");
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.inventory_mutated).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_primary).toBe(false);
  });
});
