/**
 * ModelDecisionTwinSearchHtmlNativeNdTwinPanel — free-file.
 * Model decision tree + usage bar + projection over twin search HTML-native ND twin.
 * Pure advisory — live_router_authorized/secrets_stored always false.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeModelDecisionTwinSearchHtmlNativeNdTwin,
  formatModelDecisionTwinSearchHtmlNativeNdTwinSummary,
  type ModelDecisionTwinSearchHtmlNativeNdTwinCompose,
} from "../../api/modelDecisionTwinSearchHtmlNativeNdTwinCompose";

export default function ModelDecisionTwinSearchHtmlNativeNdTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ModelDecisionTwinSearchHtmlNativeNdTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      // Compact smoke — full nest proven in pure vitest.
      setResult(
        composeModelDecisionTwinSearchHtmlNativeNdTwin({
          decision: {
            selected_model_id: "gpt-5.5",
            models: [
              {
                model_id: "gpt-5.5",
                projected_cost_usd_high: 2,
                projected_cost_usd_low: 1,
              },
              {
                model_id: "composer-2.5",
                projected_cost_usd_high: 0.5,
              },
            ],
            daily_cap_usd: 50,
            spent_usd: 10,
            projected_cost_usd_high: 2,
            projected_cost_usd_low: 1,
            focus_task: "deep_research",
          },
          twin_search_pack: {
            search_query: "scaling noise",
            twin_records: [
              {
                twin_id: "t1",
                parent_asset_id: "book-1",
                insights: ["scaling laws hold under noise"],
                questions: ["Where does it break?"],
              },
            ],
            html_pack: {
              html_view: {
                session_id: "sess-1",
                asset_id: "book-1",
                html_projection_sha: "sha",
                view_requested: true,
                twin_bound: true,
                twin_substrate_ready: true,
                claimed_format: "html",
              },
              market_pack: {
                market: {
                  title: "Scaling Laws Book",
                  account_id: "acct-1",
                  free_copy_available: true,
                  free_html_projection_sha: "sha-free",
                  purchase_ack: false,
                  port_requested: true,
                },
                settings_pack: {
                  settings: {
                    models: [{ model_id: "gpt-5.5" }],
                    pending_add_model_ids: ["mimo-v2"],
                    action: "propose_add",
                    daily_cap_usd: 50,
                    spent_usd: 10,
                    selected_model_id: "gpt-5.5",
                    projected_cost_usd_high: 2,
                  },
                  nd_pack: {
                    nd_shadow: {
                      selected_model_id: "gpt-5.5",
                      nd_recommended_model_id: "claude-opus",
                      kill_switch_on: true,
                      inventory_model_ids: ["gpt-5.5", "claude-opus"],
                      task: "deep_research",
                    },
                    twin_presentation: {
                      twin: {
                        parent_asset_id: "book-1",
                        source_excerpt: "<p>x</p>",
                        focus_questions: ["?"],
                      },
                      presentation: {
                        view_mode: "side_panel",
                        open_requested: true,
                        presented_insights: ["i"],
                        presented_questions: ["q"],
                      },
                      competition_pack: {
                        competition: {
                          session_id: "sess-1",
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
                          would_exceed: false,
                        },
                        source_pack: {
                          sources: {
                            session_id: "sess-1",
                            parent_asset_id: "book-1",
                            requested_families: ["arxiv", "substack"],
                            sources: [
                              {
                                source_id: "s1",
                                family: "arxiv",
                                title: "Scaling Laws for Neural Language Models",
                                external_id: "arxiv:2001.08361",
                                html_fragment: "<article>a</article>",
                              },
                              {
                                source_id: "s2",
                                family: "substack",
                                title: "Evals that matter",
                                external_id: "substack:evals",
                                url: "https://example.substack.com/p/evals",
                              },
                            ],
                          },
                          recommend_pack: {
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
                              ],
                              models: [
                                {
                                  model_id: "gpt-5.5",
                                  projected_cost_usd_high: 0.5,
                                },
                              ],
                              daily_cap_usd: 20,
                              spent_usd: 5,
                              projected_cost_usd_high: 0.5,
                              existing_tasks: ["deep_research"],
                            },
                            mo_pack: {
                              mo: {
                                operator_id: "op-1",
                                work_minutes: 120,
                                goals: [
                                  { goal_id: "g1", title: "Map gaps" },
                                  { goal_id: "g2", title: "Synth hits" },
                                ],
                                usd_per_hour: 15,
                                approved_ceiling_usd: 50,
                                unattended_ack: true,
                                spend_consent: true,
                              },
                              fullscreen_pack: {
                                fullscreen: {
                                  session_id: "sess-1",
                                  parent_asset_id: "book-1",
                                  highlight: "Scaling laws",
                                  gated: false,
                                },
                                draft_pack: {
                                  draft_gate: {
                                    session_id: "sess-1",
                                    parent_asset_id: "book-1",
                                    sources: [
                                      {
                                        instance_id: "a",
                                        parent_asset_id: "book-1",
                                        status: "completed",
                                        findings: ["e"],
                                      },
                                    ],
                                    stage: "draft_only",
                                  },
                                  multi_pack: {
                                    multiselect: {
                                      session_id: "sess-1",
                                      parent_asset_id: "book-1",
                                      members: [
                                        {
                                          instance_id: "a",
                                          parent_asset_id: "book-1",
                                          status: "open",
                                          highlight: "a",
                                        },
                                        {
                                          instance_id: "b",
                                          parent_asset_id: "book-1",
                                          status: "completed",
                                          highlight: "b",
                                          findings: ["f"],
                                        },
                                      ],
                                      selected_instance_ids: ["a", "b"],
                                      pack_mode: "cohesive_prompt",
                                      cohesive_prompt: "S",
                                    },
                                    decision_pack: {
                                      decision: {
                                        selected_model_id: "gpt-5.5",
                                        models: [
                                          {
                                            model_id: "gpt-5.5",
                                            projected_cost_usd_high: 2,
                                          },
                                        ],
                                        daily_cap_usd: 50,
                                        spent_usd: 10,
                                        projected_cost_usd_high: 2,
                                        focus_task: "deep_research",
                                      },
                                      twin_search_pack: {
                                        search_query: "scaling",
                                        twin_records: [
                                          {
                                            twin_id: "t1",
                                            parent_asset_id: "book-1",
                                            insights: ["i"],
                                            questions: ["q"],
                                          },
                                        ],
                                        html_pack: {
                                          html_view: {
                                            session_id: "sess-1",
                                            asset_id: "book-1",
                                            html_projection_sha: "sha",
                                            view_requested: true,
                                            twin_bound: true,
                                            twin_substrate_ready: true,
                                            claimed_format: "html",
                                          },
                                          market_pack: {
                                            market: {
                                              title: "Book",
                                              account_id: "acct-1",
                                              free_copy_available: true,
                                              free_html_projection_sha: "sha",
                                              purchase_ack: false,
                                              port_requested: true,
                                            },
                                            settings_pack: {
                                              settings: {
                                                models: [
                                                  { model_id: "gpt-5.5" },
                                                ],
                                                action: "preview",
                                                daily_cap_usd: 25,
                                                spent_usd: 4,
                                                selected_model_id: "gpt-5.5",
                                              },
                                              nd_pack: {
                                                nd_shadow: {
                                                  selected_model_id: "gpt-5.5",
                                                  nd_recommended_model_id:
                                                    "claude-opus",
                                                  kill_switch_on: true,
                                                  inventory_model_ids: [
                                                    "gpt-5.5",
                                                    "claude-opus",
                                                  ],
                                                  task: "deep_research",
                                                },
                                                competition_pack: {
                                                  competition: {
                                                    session_id: "sess-1",
                                                    competitor_decisions: [
                                                      {
                                                        competitor: "Perplexity",
                                                        area: "citation_grounding",
                                                        decision_summary:
                                                          "Inline",
                                                        antiek_status: "parity",
                                                      },
                                                      {
                                                        competitor: "OpenAI DR",
                                                        area: "multi_agent_orchestration",
                                                        decision_summary:
                                                          "Agents",
                                                        antiek_status: "behind",
                                                        residual: "cohesion",
                                                      },
                                                    ],
                                                    requested_families: [
                                                      "arxiv",
                                                      "substack",
                                                    ],
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
                                                    would_exceed: false,
                                                  },
                                                  mo_pack: {
                                                    mo: {
                                                      operator_id: "op-1",
                                                      work_minutes: 120,
                                                      goals: [
                                                        {
                                                          goal_id: "g1",
                                                          title: "Map",
                                                        },
                                                        {
                                                          goal_id: "g2",
                                                          title: "Synth",
                                                        },
                                                      ],
                                                      usd_per_hour: 15,
                                                      approved_ceiling_usd: 50,
                                                      unattended_ack: true,
                                                      spend_consent: true,
                                                    },
                                                    research_pack: {
                                                      sources: {
                                                        session_id: "sess-1",
                                                        parent_asset_id:
                                                          "book-1",
                                                        requested_families: [
                                                          "arxiv",
                                                        ],
                                                        sources: [
                                                          {
                                                            source_id: "s1",
                                                            family: "arxiv",
                                                            title: "S",
                                                            external_id:
                                                              "arxiv:1",
                                                            html_fragment:
                                                              "<article>a</article>",
                                                          },
                                                        ],
                                                      },
                                                      decision_pack: {
                                                        decision: {
                                                          selected_model_id:
                                                            "gpt-5.5",
                                                          models: [
                                                            {
                                                              model_id:
                                                                "gpt-5.5",
                                                              projected_cost_usd_high: 2,
                                                            },
                                                          ],
                                                          daily_cap_usd: 50,
                                                          spent_usd: 10,
                                                        },
                                                        twin_search_pack: {
                                                          search_query:
                                                            "scaling",
                                                          twin_records: [
                                                            {
                                                              twin_id: "t1",
                                                              parent_asset_id:
                                                                "book-1",
                                                              insights: ["i"],
                                                              questions: ["q"],
                                                            },
                                                          ],
                                                          weekly_html: {
                                                            weekly_learn: {
                                                              week_id:
                                                                "2026-W28",
                                                              min_events_per_task: 2,
                                                              events: [
                                                                {
                                                                  event_id: "e1",
                                                                  task: "deep_research",
                                                                  model_id:
                                                                    "gpt-5",
                                                                  outcome:
                                                                    "failed",
                                                                },
                                                                {
                                                                  event_id: "e2",
                                                                  task: "deep_research",
                                                                  model_id:
                                                                    "gpt-5",
                                                                  outcome:
                                                                    "failed",
                                                                },
                                                                {
                                                                  event_id: "e3",
                                                                  task: "twin_notes",
                                                                  model_id:
                                                                    "claude",
                                                                  outcome:
                                                                    "worked",
                                                                },
                                                                {
                                                                  event_id: "e4",
                                                                  task: "twin_notes",
                                                                  model_id:
                                                                    "claude",
                                                                  outcome:
                                                                    "worked",
                                                                },
                                                              ],
                                                            },
                                                            html_pack: {
                                                              html_view: {
                                                                session_id:
                                                                  "sess-1",
                                                                asset_id:
                                                                  "book-1",
                                                                html_projection_sha:
                                                                  "sha",
                                                                view_requested: true,
                                                                twin_bound: true,
                                                                twin_substrate_ready: true,
                                                                claimed_format:
                                                                  "html",
                                                              },
                                                              twin_pack: {
                                                                twin: {
                                                                  parent_asset_id:
                                                                    "book-1",
                                                                  source_excerpt:
                                                                    "<p>x</p>",
                                                                  focus_questions: [
                                                                    "?",
                                                                  ],
                                                                },
                                                                settings_pack: {
                                                                  settings: {
                                                                    models: [
                                                                      {
                                                                        model_id:
                                                                          "gpt-5.5",
                                                                      },
                                                                    ],
                                                                    action:
                                                                      "preview",
                                                                    daily_cap_usd: 25,
                                                                    spent_usd: 4,
                                                                    selected_model_id:
                                                                      "gpt-5.5",
                                                                  },
                                                                  fullscreen_mo: {
                                                                    fullscreen: {
                                                                      session_id:
                                                                        "sess-1",
                                                                      parent_asset_id:
                                                                        "book-1",
                                                                      highlight:
                                                                        "c",
                                                                      gated: false,
                                                                    },
                                                                    mo_pack: {
                                                                      mo: {
                                                                        operator_id:
                                                                          "op",
                                                                        work_minutes: 60,
                                                                        goals: [
                                                                          {
                                                                            goal_id:
                                                                              "g1",
                                                                            title:
                                                                              "A",
                                                                          },
                                                                          {
                                                                            goal_id:
                                                                              "g2",
                                                                            title:
                                                                              "B",
                                                                          },
                                                                        ],
                                                                        usd_per_hour: 30,
                                                                        price_ceiling_ack: true,
                                                                        stage:
                                                                          "recommend_only",
                                                                      },
                                                                      draft_multi: {
                                                                        draft_gate: {
                                                                          session_id:
                                                                            "sess-1",
                                                                          parent_asset_id:
                                                                            "book-1",
                                                                          sources: [
                                                                            {
                                                                              instance_id:
                                                                                "f1",
                                                                              parent_asset_id:
                                                                                "book-1",
                                                                              status:
                                                                                "completed",
                                                                              findings: [
                                                                                "e",
                                                                              ],
                                                                            },
                                                                          ],
                                                                          stage:
                                                                            "draft_only",
                                                                        },
                                                                        multi_pack: {
                                                                          multiselect: {
                                                                            session_id:
                                                                              "sess-1",
                                                                            parent_asset_id:
                                                                              "book-1",
                                                                            members: [
                                                                              {
                                                                                instance_id:
                                                                                  "a",
                                                                                parent_asset_id:
                                                                                  "book-1",
                                                                                status:
                                                                                  "open",
                                                                                highlight:
                                                                                  "a",
                                                                              },
                                                                              {
                                                                                instance_id:
                                                                                  "b",
                                                                                parent_asset_id:
                                                                                  "book-1",
                                                                                status:
                                                                                  "completed",
                                                                                highlight:
                                                                                  "b",
                                                                                findings: [
                                                                                  "f",
                                                                                ],
                                                                              },
                                                                            ],
                                                                            selected_instance_ids: [
                                                                              "a",
                                                                              "b",
                                                                            ],
                                                                            pack_mode:
                                                                              "cohesive_prompt",
                                                                            cohesive_prompt:
                                                                              "S",
                                                                          },
                                                                          record_write: {
                                                                            record_prompt: {
                                                                              session_id:
                                                                                "sess-1",
                                                                              parent_asset_id:
                                                                                "book-1",
                                                                              records: [
                                                                                {
                                                                                  record_id:
                                                                                    "r1",
                                                                                  kind: "insight",
                                                                                  body: "h",
                                                                                },
                                                                                {
                                                                                  record_id:
                                                                                    "r2",
                                                                                  kind: "question",
                                                                                  body: "g?",
                                                                                },
                                                                              ],
                                                                              user_prompt:
                                                                                "S",
                                                                              selected_model_id:
                                                                                "gpt-5",
                                                                              models: [
                                                                                {
                                                                                  model_id:
                                                                                    "gpt-5",
                                                                                  projected_cost_usd_high: 2,
                                                                                },
                                                                              ],
                                                                              daily_cap_usd: 100,
                                                                              spent_usd: 40,
                                                                              projected_cost_usd_high: 2,
                                                                            },
                                                                            write_pack: {
                                                                              write: {
                                                                                session_id:
                                                                                  "sess-1",
                                                                                draft_id:
                                                                                  "d1",
                                                                                parent_asset_id:
                                                                                  "book-1",
                                                                                twin_slices: [
                                                                                  {
                                                                                    parent_asset_id:
                                                                                      "a1",
                                                                                    insights: [
                                                                                      "i",
                                                                                    ],
                                                                                    questions: [
                                                                                      "q",
                                                                                    ],
                                                                                  },
                                                                                  {
                                                                                    parent_asset_id:
                                                                                      "a2",
                                                                                    insights: [
                                                                                      "j",
                                                                                    ],
                                                                                    questions: [],
                                                                                  },
                                                                                ],
                                                                                chase_slots: [
                                                                                  {
                                                                                    slot_id:
                                                                                      "s1",
                                                                                    question_id:
                                                                                      "q1",
                                                                                    parent_asset_id:
                                                                                      "book-1",
                                                                                    status:
                                                                                      "completed",
                                                                                    findings: [
                                                                                      "f1",
                                                                                    ],
                                                                                    body: "?",
                                                                                  },
                                                                                  {
                                                                                    slot_id:
                                                                                      "s2",
                                                                                    question_id:
                                                                                      "q2",
                                                                                    parent_asset_id:
                                                                                      "book-1",
                                                                                    status:
                                                                                      "completed",
                                                                                    findings: [
                                                                                      "f2",
                                                                                    ],
                                                                                    body: "?",
                                                                                  },
                                                                                ],
                                                                                analysis_kind:
                                                                                  "draft_analysis",
                                                                              },
                                                                              highlight_pack: {
                                                                                highlight: {
                                                                                  parent_asset_id:
                                                                                    "book-1",
                                                                                  highlight:
                                                                                    "scaling",
                                                                                  gated: false,
                                                                                  would_exceed: false,
                                                                                  preferred_view_mode:
                                                                                    "floating",
                                                                                  source_families: [
                                                                                    "arxiv",
                                                                                  ],
                                                                                },
                                                                                twin_search_pack: {
                                                                                  competition_pack: {
                                                                                    competition: {
                                                                                      session_id:
                                                                                        "sess-1",
                                                                                      competitor_decisions: [
                                                                                        {
                                                                                          competitor:
                                                                                            "Perplexity",
                                                                                          area: "citation_grounding",
                                                                                          decision_summary:
                                                                                            "Inline",
                                                                                          antiek_status:
                                                                                            "parity",
                                                                                        },
                                                                                        {
                                                                                          competitor:
                                                                                            "OpenAI DR",
                                                                                          area: "multi_agent_orchestration",
                                                                                          decision_summary:
                                                                                            "Agents",
                                                                                          antiek_status:
                                                                                            "behind",
                                                                                          residual:
                                                                                            "cohesion",
                                                                                        },
                                                                                      ],
                                                                                      requested_families: [
                                                                                        "arxiv",
                                                                                        "substack",
                                                                                      ],
                                                                                      citations: [
                                                                                        {
                                                                                          citation_id:
                                                                                            "c1",
                                                                                          family:
                                                                                            "arxiv",
                                                                                          title:
                                                                                            "S",
                                                                                          external_id:
                                                                                            "arxiv:1",
                                                                                        },
                                                                                        {
                                                                                          citation_id:
                                                                                            "c2",
                                                                                          family:
                                                                                            "substack",
                                                                                          title:
                                                                                            "N",
                                                                                          url: "https://example.substack.com/p/n",
                                                                                        },
                                                                                      ],
                                                                                      quality_overall: 0.8,
                                                                                      would_exceed: false,
                                                                                      search_query:
                                                                                        "scaling",
                                                                                    },
                                                                                    nd_weekly: {
                                                                                      nd_shadow: {
                                                                                        selected_model_id:
                                                                                          "gpt-5.5",
                                                                                        nd_recommended_model_id:
                                                                                          "claude-opus",
                                                                                        kill_switch_on: true,
                                                                                        inventory_model_ids: [
                                                                                          "gpt-5.5",
                                                                                          "claude-opus",
                                                                                        ],
                                                                                        task: "deep_research",
                                                                                      },
                                                                                      weekly_market: {
                                                                                        weekly_learn: {
                                                                                          week_id:
                                                                                            "2026-W28",
                                                                                          min_events_per_task: 2,
                                                                                          events: [
                                                                                            {
                                                                                              event_id:
                                                                                                "e1",
                                                                                              task: "deep_research",
                                                                                              model_id:
                                                                                                "gpt-5",
                                                                                              outcome:
                                                                                                "failed",
                                                                                            },
                                                                                            {
                                                                                              event_id:
                                                                                                "e2",
                                                                                              task: "deep_research",
                                                                                              model_id:
                                                                                                "gpt-5",
                                                                                              outcome:
                                                                                                "failed",
                                                                                            },
                                                                                            {
                                                                                              event_id:
                                                                                                "e3",
                                                                                              task: "twin_notes",
                                                                                              model_id:
                                                                                                "claude",
                                                                                              outcome:
                                                                                                "worked",
                                                                                            },
                                                                                            {
                                                                                              event_id:
                                                                                                "e4",
                                                                                              task: "twin_notes",
                                                                                              model_id:
                                                                                                "claude",
                                                                                              outcome:
                                                                                                "worked",
                                                                                            },
                                                                                          ],
                                                                                        },
                                                                                        market_research: {
                                                                                          market: {
                                                                                            session_id:
                                                                                              "sess-1",
                                                                                            asset_id:
                                                                                              "book-1",
                                                                                            title:
                                                                                              "Scaling",
                                                                                            account_id:
                                                                                              "acct-1",
                                                                                            free_copy_available: true,
                                                                                            free_html_projection_sha:
                                                                                              "sha",
                                                                                            port_requested: true,
                                                                                            purchase_ack: false,
                                                                                            list_price_usd: 10,
                                                                                            approved_spend_usd: 20,
                                                                                            remaining_budget_usd: 50,
                                                                                            view_requested: true,
                                                                                          },
                                                                                          research: {
                                                                                            highlight_surface: {
                                                                                              highlight:
                                                                                                "scaling",
                                                                                              gated: false,
                                                                                              would_exceed: false,
                                                                                              surface_action:
                                                                                                "spawn_only",
                                                                                              source_families: [
                                                                                                "arxiv",
                                                                                              ],
                                                                                            },
                                                                                            mo_competition: {
                                                                                              mo: {
                                                                                                operator_id:
                                                                                                  "op-1",
                                                                                                work_minutes: 120,
                                                                                                goals: [
                                                                                                  {
                                                                                                    goal_id:
                                                                                                      "g1",
                                                                                                    title:
                                                                                                      "Survey",
                                                                                                  },
                                                                                                  {
                                                                                                    goal_id:
                                                                                                      "g2",
                                                                                                    title:
                                                                                                      "Draft",
                                                                                                  },
                                                                                                ],
                                                                                                usd_per_hour: 15,
                                                                                                approved_ceiling_usd: 40,
                                                                                                unattended_ack: true,
                                                                                                spend_consent: true,
                                                                                              },
                                                                                              research: {
                                                                                                decision: {
                                                                                                  selected_model_id:
                                                                                                    "gpt-5.5",
                                                                                                  models: [
                                                                                                    {
                                                                                                      model_id:
                                                                                                        "gpt-5.5",
                                                                                                      projected_cost_usd_high: 2,
                                                                                                    },
                                                                                                  ],
                                                                                                  daily_cap_usd: 50,
                                                                                                  spent_usd: 10,
                                                                                                },
                                                                                                competition_view: {
                                                                                                  session_id:
                                                                                                    "sess-1",
                                                                                                  asset_id:
                                                                                                    "book-1",
                                                                                                  html_projection_sha:
                                                                                                    "sha",
                                                                                                  view_requested: true,
                                                                                                  twin_bound: true,
                                                                                                  claimed_format:
                                                                                                    "html",
                                                                                                  competition: {
                                                                                                    draft_id:
                                                                                                      "d1",
                                                                                                    parent_asset_id:
                                                                                                      "book-1",
                                                                                                    competitor_decisions: [
                                                                                                      {
                                                                                                        competitor:
                                                                                                          "Perplexity",
                                                                                                        area: "citation_grounding",
                                                                                                        decision_summary:
                                                                                                          "Inline",
                                                                                                        antiek_status:
                                                                                                          "parity",
                                                                                                      },
                                                                                                      {
                                                                                                        competitor:
                                                                                                          "OpenAI DR",
                                                                                                        area: "multi_agent_orchestration",
                                                                                                        decision_summary:
                                                                                                          "Agents",
                                                                                                        antiek_status:
                                                                                                          "behind",
                                                                                                        residual:
                                                                                                          "cohesion",
                                                                                                      },
                                                                                                    ],
                                                                                                    requested_families: [
                                                                                                      "arxiv",
                                                                                                      "substack",
                                                                                                    ],
                                                                                                    citations: [
                                                                                                      {
                                                                                                        citation_id:
                                                                                                          "c1",
                                                                                                        family:
                                                                                                          "arxiv",
                                                                                                        title:
                                                                                                          "S",
                                                                                                        external_id:
                                                                                                          "arxiv:1",
                                                                                                      },
                                                                                                      {
                                                                                                        citation_id:
                                                                                                          "c2",
                                                                                                        family:
                                                                                                          "substack",
                                                                                                        title:
                                                                                                          "N",
                                                                                                        url: "https://example.substack.com/p/n",
                                                                                                      },
                                                                                                    ],
                                                                                                    quality_overall: 0.8,
                                                                                                    would_exceed: false,
                                                                                                    search_query:
                                                                                                      "scaling",
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
    <LemonCard
      className="p-4 space-y-3"
      data-testid="model-decision-twin-search-html-native-nd-twin-panel"
    >
      <h2 className="text-lg font-semibold">
        Model decision · twin search HTML-native ND twin
      </h2>
      <p className="text-sm text-muted">
        Pure advisory — live_router_authorized / secrets_stored always false.
        Budget would_exceed blocks pack. Full nest in pure tests.
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
        Compose model decision pack
      </LemonButton>
      {error && (
        <pre className="text-xs text-danger whitespace-pre-wrap">{error}</pre>
      )}
      {result && (
        <div className="space-y-2 text-sm">
          <div data-testid="summary">
            {formatModelDecisionTwinSearchHtmlNativeNdTwinSummary(result)}
          </div>
          <div>
            pack_ready=<strong>{String(result.pack_ready)}</strong> ·
            decision_ready=
            <strong>{String(result.decision.decision_ready)}</strong> ·
            would_exceed=
            <strong>{String(result.decision.would_exceed)}</strong>
          </div>
          <div>
            live_router={String(result.live_router_authorized)} · secrets=
            {String(result.secrets_stored)} · verdict=
            {result.production_router_verdict}
          </div>
        </div>
      )}
    </LemonCard>
  );
}
