/**
 * SourceAttachAntiekBenchRewriteModelDecisionPanel — free-file.
 * arxiv/substack HTML source attach over Antiek-bench rewrite + model decision.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSourceAttachAntiekBenchRewriteModelDecision,
  formatSourceAttachAntiekBenchRewriteModelDecisionSummary,
  type SourceAttachAntiekBenchRewriteModelDecisionCompose,
} from "../../api/sourceAttachAntiekBenchRewriteModelDecisionCompose";

export default function SourceAttachAntiekBenchRewriteModelDecisionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourceAttachAntiekBenchRewriteModelDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      // Compact demo — full nest proven in pure tests.
      setResult(
        composeSourceAttachAntiekBenchRewriteModelDecision({
          sources: {
            session_id: "sess-demo",
            parent_asset_id: "book-demo",
            requested_families: ["arxiv", "substack"],
            sources: [
              {
                source_id: "arx-1",
                family: "arxiv",
                title: "Scaling Laws",
                external_id: "arxiv:1",
                html_fragment: "<article>a</article>",
              },
              {
                source_id: "sub-1",
                family: "substack",
                title: "Notes",
                url: "https://example.substack.com/p/n",
                html_fragment: "<article>b</article>",
              },
            ],
          },
          rewrite_pack: {
            rewrite: {
              week_label: "2026-W28",
              patterns: [
                {
                  task_family: "deep_research",
                  model_id: "gpt-5",
                  outcome: "failed",
                  n: 3,
                },
              ],
            },
            model_decision_pack: {
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
                projected_cost_usd_high: 2,
                projected_cost_usd_low: 1,
                focus_task: "deep_research",
              },
              twin_search_pack: {
                search_query: "scaling",
                twin_records: [
                  {
                    twin_id: "t1",
                    parent_asset_id: "book-demo",
                    insights: ["holds"],
                    questions: ["break?"],
                  },
                ],
                html_pack: {
                  html_view: {
                    session_id: "sess-demo",
                    asset_id: "book-demo",
                    html_projection_sha: "sha",
                    view_requested: true,
                    twin_bound: true,
                    twin_substrate_ready: true,
                    claimed_format: "html",
                  },
                  twin_pack: {
                    twin: {
                      parent_asset_id: "book-demo",
                      source_excerpt: "<p>S</p>",
                      focus_questions: ["?"],
                    },
                    market_pack: {
                      market: {
                        title: "Book",
                        account_id: "acct",
                        free_copy_available: true,
                        free_html_projection_sha: "sha-free",
                        purchase_ack: false,
                        port_requested: true,
                      },
                      competition_pack: {
                        competition: {
                          session_id: "sess-demo",
                          competitor_decisions: [
                            {
                              competitor: "Perplexity",
                              area: "citation_grounding",
                              decision_summary: "Inline",
                              antiek_status: "parity",
                            },
                            {
                              competitor: "OpenAI DR",
                              area: "multi_agent_orchestration",
                              decision_summary: "Agents",
                              antiek_status: "behind",
                              residual: "cohesion",
                            },
                          ],
                          requested_families: ["arxiv", "substack"],
                          citations: [
                            {
                              citation_id: "c1",
                              family: "arxiv",
                              title: "S",
                              external_id: "arxiv:1",
                            },
                            {
                              citation_id: "c2",
                              family: "substack",
                              title: "N",
                              url: "https://example.substack.com/p/n",
                            },
                          ],
                          quality_overall: 0.8,
                          quality_floor: 0.5,
                          would_exceed: false,
                        },
                        settings_pack: {
                          settings: {
                            models: [{ model_id: "gpt-5.5", provider: "openai" }],
                            pending_add_model_ids: ["mimo-v2"],
                            action: "propose_add",
                            daily_cap_usd: 50,
                            spent_usd: 10,
                            selected_model_id: "gpt-5.5",
                            projected_cost_usd_high: 2,
                            projected_cost_usd_low: 1,
                          },
                          bench_pack: {
                            bench: {
                              week_id: "2026-W28",
                              focus_task: "deep_research",
                              events: [
                                {
                                  event_id: "e1",
                                  task: "deep_research",
                                  model_id: "gpt-5.5",
                                  outcome: "worked",
                                  score: 0.9,
                                },
                                {
                                  event_id: "e2",
                                  task: "deep_research",
                                  model_id: "gpt-5.5",
                                  outcome: "worked",
                                  score: 0.85,
                                },
                                {
                                  event_id: "e3",
                                  task: "deep_research",
                                  model_id: "mimo-v2",
                                  outcome: "failed",
                                  score: 0.2,
                                },
                                {
                                  event_id: "e4",
                                  task: "deep_research",
                                  model_id: "mimo-v2",
                                  outcome: "failed",
                                  score: 0.3,
                                },
                                {
                                  event_id: "e5",
                                  task: "twin_notes",
                                  model_id: "grok-4.5",
                                  outcome: "worked",
                                  score: 0.8,
                                },
                                {
                                  event_id: "e6",
                                  task: "twin_notes",
                                  model_id: "grok-4.5",
                                  outcome: "worked",
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
                            },
                            source_pack: {
                              sources: {
                                session_id: "sess-demo",
                                parent_asset_id: "book-demo",
                                requested_families: ["arxiv", "substack"],
                                sources: [
                                  {
                                    source_id: "arx-1",
                                    family: "arxiv",
                                    title: "S",
                                    external_id: "arxiv:1",
                                    html_fragment: "<article>a</article>",
                                  },
                                  {
                                    source_id: "sub-1",
                                    family: "substack",
                                    title: "N",
                                    url: "https://example.substack.com/p/n",
                                    html_fragment: "<article>b</article>",
                                  },
                                ],
                              },
                              settings_mo: {
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
                                  projected_cost_usd_high: 2,
                                  projected_cost_usd_low: 1,
                                  focus_task: "deep_research",
                                },
                                mo_pack: {
                                  mo: {
                                    operator_id: "op-1",
                                    work_minutes: 120,
                                    goals: [
                                      { goal_id: "g1", title: "Map" },
                                      { goal_id: "g2", title: "Synth" },
                                    ],
                                    usd_per_hour: 15,
                                    approved_ceiling_usd: 40,
                                    unattended_ack: true,
                                    spend_consent: true,
                                    brief_dispatch_ready: true,
                                  },
                                  fullscreen_pack: {
                                    fullscreen: {
                                      session_id: "sess-demo",
                                      parent_asset_id: "book-demo",
                                      highlight: "claim",
                                      prompt: "?",
                                      gated: false,
                                    },
                                    draft_collective: {
                                      draft_gate: {
                                        session_id: "sess-demo",
                                        parent_asset_id: "book-demo",
                                        parent_excerpt: "<p>P</p>",
                                        sources: [
                                          {
                                            instance_id: "f1",
                                            parent_asset_id: "book-demo",
                                            status: "completed",
                                            highlight: "k",
                                            findings: ["A"],
                                          },
                                        ],
                                        stage: "draft_only",
                                      },
                                      collective_pack: {
                                        collective: {
                                          session_id: "sess-demo",
                                          parent_asset_id: "book-demo",
                                          members: [
                                            {
                                              instance_id: "a",
                                              parent_asset_id: "book-demo",
                                              status: "open",
                                              highlight: "a",
                                            },
                                            {
                                              instance_id: "b",
                                              parent_asset_id: "book-demo",
                                              status: "completed",
                                              highlight: "b",
                                              findings: ["b1"],
                                            },
                                          ],
                                          selected_instance_ids: ["a", "b"],
                                          pack_mode: "cohesive_prompt",
                                          cohesive_prompt: "Synth",
                                        },
                                        paid_nd: {
                                          purchase: {
                                            title: "Book",
                                            account_id: "acct",
                                            free_copy_available: true,
                                            free_html_projection_sha: "sha",
                                            purchase_ack: false,
                                            port_requested: true,
                                            list_price_usd: 10,
                                            approved_spend_usd: 20,
                                            remaining_budget_usd: 50,
                                          },
                                          nd_twin: {
                                            nd_shadow: {
                                              selected_model_id: "gpt-5.5",
                                              nd_recommended_model_id: "claude-opus",
                                              kill_switch_on: true,
                                              confidence: 0.7,
                                              task: "deep_research",
                                              inventory_model_ids: ["gpt-5.5", "claude-opus"],
                                            },
                                            twin_presentation: {
                                              twin: {
                                                parent_asset_id: "book-demo",
                                                source_excerpt: "<p>S</p>",
                                                focus_questions: ["?"],
                                              },
                                              presentation: {
                                                view_mode: "side_panel",
                                                open_requested: true,
                                                merge_to_parent_preview: false,
                                                presented_insights: ["holds"],
                                                presented_questions: ["?"],
                                              },
                                              competition_pack: {
                                                competition: {
                                                  session_id: "sess-demo",
                                                  competitor_decisions: [
                                                    {
                                                      competitor: "Perplexity",
                                                      area: "citation_grounding",
                                                      decision_summary: "I",
                                                      antiek_status: "parity",
                                                    },
                                                    {
                                                      competitor: "OpenAI DR",
                                                      area: "multi_agent_orchestration",
                                                      decision_summary: "A",
                                                      antiek_status: "behind",
                                                      residual: "c",
                                                    },
                                                  ],
                                                  requested_families: ["arxiv", "substack"],
                                                  citations: [
                                                    {
                                                      citation_id: "c1",
                                                      family: "arxiv",
                                                      title: "S",
                                                      external_id: "arxiv:1",
                                                    },
                                                    {
                                                      citation_id: "c2",
                                                      family: "substack",
                                                      title: "N",
                                                      url: "https://example.substack.com/p/n",
                                                    },
                                                  ],
                                                  quality_overall: 0.8,
                                                  quality_floor: 0.5,
                                                  would_exceed: false,
                                                },
                                                free_pack: {
                                                  market: {
                                                    title: "Book",
                                                    account_id: "acct",
                                                    free_copy_available: true,
                                                    free_html_projection_sha: "sha",
                                                    purchase_ack: false,
                                                    port_requested: true,
                                                  },
                                                  bench_mo: {
                                                    bench: {
                                                      week_id: "2026-W28",
                                                      focus_task: "deep_research",
                                                      events: [
                                                        {
                                                          event_id: "e1",
                                                          task: "deep_research",
                                                          model_id: "gpt-5.5",
                                                          outcome: "worked",
                                                          score: 0.9,
                                                        },
                                                        {
                                                          event_id: "e2",
                                                          task: "deep_research",
                                                          model_id: "gpt-5.5",
                                                          outcome: "worked",
                                                          score: 0.85,
                                                        },
                                                        {
                                                          event_id: "e3",
                                                          task: "deep_research",
                                                          model_id: "mimo-v2",
                                                          outcome: "failed",
                                                          score: 0.2,
                                                        },
                                                        {
                                                          event_id: "e4",
                                                          task: "deep_research",
                                                          model_id: "mimo-v2",
                                                          outcome: "failed",
                                                          score: 0.3,
                                                        },
                                                        {
                                                          event_id: "e5",
                                                          task: "twin_notes",
                                                          model_id: "grok-4.5",
                                                          outcome: "worked",
                                                          score: 0.8,
                                                        },
                                                        {
                                                          event_id: "e6",
                                                          task: "twin_notes",
                                                          model_id: "grok-4.5",
                                                          outcome: "worked",
                                                          score: 0.75,
                                                        },
                                                      ],
                                                      models: [
                                                        {
                                                          model_id: "gpt-5.5",
                                                          projected_cost_usd_high: 0.5,
                                                        },
                                                        {
                                                          model_id: "grok-4.5",
                                                          projected_cost_usd_high: 0.3,
                                                        },
                                                        {
                                                          model_id: "mimo-v2",
                                                          projected_cost_usd_high: 0.1,
                                                        },
                                                      ],
                                                      daily_cap_usd: 20,
                                                      spent_usd: 5,
                                                      projected_cost_usd_high: 0.5,
                                                      existing_tasks: [
                                                        "deep_research",
                                                        "twin_notes",
                                                      ],
                                                    },
                                                    mo_pack: {
                                                      mo: {
                                                        operator_id: "op-1",
                                                        work_minutes: 120,
                                                        goals: [
                                                          { goal_id: "g1", title: "M" },
                                                          { goal_id: "g2", title: "S" },
                                                        ],
                                                        usd_per_hour: 30,
                                                        approved_ceiling_usd: 500,
                                                        price_ceiling_ack: true,
                                                        unattended_ack: true,
                                                        spend_consent: true,
                                                        stage: "unattended_pack",
                                                      },
                                                      research_pack: {
                                                        sources: {
                                                          session_id: "sess-demo",
                                                          parent_asset_id: "book-demo",
                                                          requested_families: [
                                                            "arxiv",
                                                            "substack",
                                                          ],
                                                          sources: [
                                                            {
                                                              source_id: "arx-1",
                                                              family: "arxiv",
                                                              title: "S",
                                                              external_id: "arxiv:1",
                                                              html_fragment:
                                                                "<article>a</article>",
                                                            },
                                                            {
                                                              source_id: "sub-1",
                                                              family: "substack",
                                                              title: "N",
                                                              url: "https://example.substack.com/p/n",
                                                              html_fragment:
                                                                "<article>b</article>",
                                                            },
                                                          ],
                                                        },
                                                        decision_pack: {
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
                                                            projected_cost_usd_high: 2,
                                                            projected_cost_usd_low: 1,
                                                            focus_task: "deep_research",
                                                          },
                                                          twin_search_pack: {
                                                            search_query: "scaling",
                                                            twin_records: [
                                                              {
                                                                twin_id: "t1",
                                                                parent_asset_id:
                                                                  "book-demo",
                                                                insights: ["holds"],
                                                                questions: ["?"],
                                                              },
                                                            ],
                                                            weekly_html: {
                                                              weekly_learn: {
                                                                week_id: "2026-W28",
                                                                min_events_per_task: 2,
                                                                events: [
                                                                  {
                                                                    event_id: "e1",
                                                                    task: "deep_research",
                                                                    model_id: "gpt-5",
                                                                    outcome: "failed",
                                                                  },
                                                                  {
                                                                    event_id: "e2",
                                                                    task: "deep_research",
                                                                    model_id: "gpt-5",
                                                                    outcome: "failed",
                                                                  },
                                                                  {
                                                                    event_id: "e3",
                                                                    task: "twin_notes",
                                                                    model_id: "claude",
                                                                    outcome: "worked",
                                                                  },
                                                                  {
                                                                    event_id: "e4",
                                                                    task: "twin_notes",
                                                                    model_id: "claude",
                                                                    outcome: "worked",
                                                                  },
                                                                ],
                                                              },
                                                              html_pack: {
                                                                html_view: {
                                                                  session_id: "sess-demo",
                                                                  asset_id: "book-demo",
                                                                  html_projection_sha: "sha",
                                                                  view_requested: true,
                                                                  twin_bound: true,
                                                                  twin_substrate_ready: true,
                                                                  claimed_format: "html",
                                                                },
                                                                twin_pack: {
                                                                  twin: {
                                                                    parent_asset_id:
                                                                      "book-demo",
                                                                    source_excerpt: "<p>S</p>",
                                                                    focus_questions: ["?"],
                                                                  },
                                                                  settings_pack: {
                                                                    settings: {
                                                                      models: [
                                                                        {
                                                                          model_id: "gpt-5.5",
                                                                          provider: "openai",
                                                                        },
                                                                      ],
                                                                      pending_add_model_ids: [
                                                                        "mimo-v2",
                                                                      ],
                                                                      action: "preview",
                                                                      daily_cap_usd: 25,
                                                                      spent_usd: 4,
                                                                      selected_model_id:
                                                                        "gpt-5.5",
                                                                      projected_cost_usd_high: 2,
                                                                      projected_cost_usd_low: 1,
                                                                    },
                                                                    fullscreen_mo: {
                                                                      fullscreen: {
                                                                        session_id:
                                                                          "sess-demo",
                                                                        parent_asset_id:
                                                                          "book-demo",
                                                                        highlight: "c",
                                                                        prompt: "?",
                                                                        gated: false,
                                                                      },
                                                                      mo_pack: {
                                                                        mo: {
                                                                          operator_id: "op-1",
                                                                          work_minutes: 120,
                                                                          goals: [
                                                                            {
                                                                              goal_id: "g1",
                                                                              title: "M",
                                                                            },
                                                                            {
                                                                              goal_id: "g2",
                                                                              title: "S",
                                                                            },
                                                                          ],
                                                                          usd_per_hour: 30,
                                                                          price_ceiling_ack: true,
                                                                          stage: "recommend_only",
                                                                        },
                                                                        draft_multi: {
                                                                          draft_gate: {
                                                                            session_id:
                                                                              "sess-demo",
                                                                            parent_asset_id:
                                                                              "book-demo",
                                                                            parent_excerpt:
                                                                              "<p>P</p>",
                                                                            sources: [
                                                                              {
                                                                                instance_id: "f1",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                status:
                                                                                  "completed",
                                                                                highlight: "k",
                                                                                findings: ["A"],
                                                                              },
                                                                            ],
                                                                            stage: "draft_only",
                                                                          },
                                                                          multi_pack: {
                                                                            multiselect: {
                                                                              session_id:
                                                                                "sess-demo",
                                                                              parent_asset_id:
                                                                                "book-demo",
                                                                              members: [
                                                                                {
                                                                                  instance_id: "a",
                                                                                  parent_asset_id:
                                                                                    "book-demo",
                                                                                  status: "open",
                                                                                  highlight: "a",
                                                                                },
                                                                                {
                                                                                  instance_id: "b",
                                                                                  parent_asset_id:
                                                                                    "book-demo",
                                                                                  status:
                                                                                    "completed",
                                                                                  highlight: "b",
                                                                                  findings: ["b1"],
                                                                                },
                                                                              ],
                                                                              selected_instance_ids: [
                                                                                "a",
                                                                                "b",
                                                                              ],
                                                                              pack_mode:
                                                                                "cohesive_prompt",
                                                                              cohesive_prompt: "S",
                                                                            },
                                                                            record_write: {
                                                                              record_prompt: {
                                                                                session_id:
                                                                                  "sess-demo",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                records: [
                                                                                  {
                                                                                    record_id: "r1",
                                                                                    kind: "insight",
                                                                                    body: "h",
                                                                                  },
                                                                                  {
                                                                                    record_id: "r2",
                                                                                    kind: "question",
                                                                                    body: "?",
                                                                                  },
                                                                                ],
                                                                                user_prompt: "Sum",
                                                                                selected_model_id:
                                                                                  "gpt-5",
                                                                                models: [
                                                                                  {
                                                                                    model_id:
                                                                                      "gpt-5",
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
                                                                                  session_id:
                                                                                    "sess-demo",
                                                                                  draft_id: "d1",
                                                                                  parent_asset_id:
                                                                                    "book-demo",
                                                                                  twin_slices: [
                                                                                    {
                                                                                      parent_asset_id:
                                                                                        "a1",
                                                                                      insights: ["h"],
                                                                                      questions: ["?"],
                                                                                    },
                                                                                    {
                                                                                      parent_asset_id:
                                                                                        "a2",
                                                                                      insights: ["a"],
                                                                                      questions: [],
                                                                                    },
                                                                                  ],
                                                                                  base_draft_html:
                                                                                    "<p>O</p>",
                                                                                  chase_slots: [
                                                                                    {
                                                                                      slot_id: "s1",
                                                                                      question_id:
                                                                                        "q1",
                                                                                      parent_asset_id:
                                                                                        "book-demo",
                                                                                      status:
                                                                                        "completed",
                                                                                      findings: ["A"],
                                                                                      body: "?",
                                                                                    },
                                                                                    {
                                                                                      slot_id: "s2",
                                                                                      question_id:
                                                                                        "q2",
                                                                                      parent_asset_id:
                                                                                        "book-demo",
                                                                                      status:
                                                                                        "completed",
                                                                                      findings: ["B"],
                                                                                      body: "?",
                                                                                    },
                                                                                  ],
                                                                                  analysis_kind:
                                                                                    "draft_analysis",
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
              },
            },
          },
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Source attach · Antiek-bench rewrite · model decision
      </h2>
      <p className="text-sm text-muted">
        Pure residual: arxiv/substack HTML attach over recursive rewrite + model
        decision marketplace. remote_fetched=false · suite_rewritten=false · ND
        REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose source-attach residual pack
      </LemonButton>
      {error && (
        <LemonCard className="border-danger p-3 text-sm text-danger">
          {error}
        </LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm space-y-1">
          <div>
            {formatSourceAttachAntiekBenchRewriteModelDecisionSummary(result)}
          </div>
          <div>pack_ready={String(result.pack_ready)}</div>
          <div>attach_ready={String(result.attach_ready)}</div>
          <div>remote_fetched={String(result.remote_fetched)}</div>
          <div>suite_rewritten={String(result.suite_rewritten)}</div>
          <div>
            production_router_verdict={result.production_router_verdict}
          </div>
        </LemonCard>
      )}
    </div>
  );
}
