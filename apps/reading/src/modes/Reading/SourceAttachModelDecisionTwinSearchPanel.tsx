/**
 * SourceAttachModelDecisionTwinSearchPanel — free-file.
 * HTML-native arxiv/substack attach over model decision + twin search weekly.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSourceAttachModelDecisionTwinSearch,
  formatSourceAttachModelDecisionTwinSearchSummary,
  type SourceAttachModelDecisionTwinSearchCompose,
} from "../../api/sourceAttachModelDecisionTwinSearchCompose";

export default function SourceAttachModelDecisionTwinSearchPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourceAttachModelDecisionTwinSearchCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeSourceAttachModelDecisionTwinSearch({
          sources: {
            session_id: "sess-demo",
            parent_asset_id: "book-demo",
            requested_families: ["arxiv", "substack"],
            sources: [
              {
                source_id: "arx-1",
                family: "arxiv",
                title: "Scaling Laws under Noise",
                external_id: "arxiv:1",
                html_fragment: "<article>a</article>",
              },
              {
                source_id: "sub-1",
                family: "substack",
                title: "Eval notes",
                url: "https://example.substack.com/p/n",
                html_fragment: "<article>e</article>",
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
                  parent_asset_id: "book-demo",
                  insights: ["scaling holds under noise"],
                  questions: ["Where does it break?"],
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
                      parent_asset_id: "book-demo",
                      source_excerpt: "<p>x</p>",
                      focus_questions: ["?"],
                    },
                    settings_pack: {
                      settings: {
                        models: [{ model_id: "gpt-5.5" }],
                        action: "preview",
                        daily_cap_usd: 25,
                        spent_usd: 4,
                        selected_model_id: "gpt-5.5",
                      },
                      fullscreen_mo: {
                        fullscreen: {
                          session_id: "sess-demo",
                          parent_asset_id: "book-demo",
                          highlight: "c",
                          gated: false,
                        },
                        mo_pack: {
                          mo: {
                            operator_id: "op",
                            work_minutes: 60,
                            goals: [
                              { goal_id: "g1", title: "A" },
                              { goal_id: "g2", title: "B" },
                            ],
                            usd_per_hour: 30,
                            price_ceiling_ack: true,
                            stage: "recommend_only",
                          },
                          draft_multi: {
                            draft_gate: {
                              session_id: "sess-demo",
                              parent_asset_id: "book-demo",
                              sources: [
                                {
                                  instance_id: "f1",
                                  parent_asset_id: "book-demo",
                                  status: "completed",
                                  findings: ["e"],
                                },
                              ],
                              stage: "draft_only",
                            },
                            multi_pack: {
                              multiselect: {
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
                                    findings: ["f"],
                                  },
                                ],
                                selected_instance_ids: ["a", "b"],
                                pack_mode: "cohesive_prompt",
                                cohesive_prompt: "S",
                              },
                              record_write: {
                                record_prompt: {
                                  session_id: "sess-demo",
                                  parent_asset_id: "book-demo",
                                  records: [
                                    {
                                      record_id: "r1",
                                      kind: "insight",
                                      body: "h",
                                    },
                                    {
                                      record_id: "r2",
                                      kind: "question",
                                      body: "g?",
                                    },
                                  ],
                                  user_prompt: "S",
                                  selected_model_id: "gpt-5",
                                  models: [
                                    {
                                      model_id: "gpt-5",
                                      projected_cost_usd_high: 2,
                                    },
                                  ],
                                  daily_cap_usd: 100,
                                  spent_usd: 40,
                                  projected_cost_usd_high: 2,
                                },
                                write_pack: {
                                  write: {
                                    session_id: "sess-demo",
                                    draft_id: "d1",
                                    parent_asset_id: "book-demo",
                                    twin_slices: [
                                      {
                                        parent_asset_id: "a1",
                                        insights: ["h"],
                                        questions: ["q"],
                                      },
                                      {
                                        parent_asset_id: "a2",
                                        insights: ["i"],
                                        questions: [],
                                      },
                                    ],
                                    chase_slots: [
                                      {
                                        slot_id: "s1",
                                        question_id: "q1",
                                        parent_asset_id: "book-demo",
                                        status: "completed",
                                        findings: ["A"],
                                        body: "E?",
                                      },
                                      {
                                        slot_id: "s2",
                                        question_id: "q2",
                                        parent_asset_id: "book-demo",
                                        status: "completed",
                                        findings: ["B"],
                                        body: "C?",
                                      },
                                    ],
                                    analysis_kind: "draft_analysis",
                                  },
                                  highlight_pack: {
                                    highlight: {
                                      parent_asset_id: "book-demo",
                                      highlight: "residual",
                                      gated: false,
                                      preferred_view_mode: "floating",
                                      source_families: ["arxiv", "substack"],
                                    },
                                    twin_search_pack: {
                                      competition_pack: {
                                        competition: {
                                          session_id: "sess-demo",
                                          competitor_decisions: [
                                            {
                                              competitor: "Perplexity",
                                              area: "citation_grounding",
                                              decision_summary: "c",
                                              antiek_status: "parity",
                                            },
                                            {
                                              competitor: "OpenAI DR",
                                              area: "multi_agent_orchestration",
                                              decision_summary: "a",
                                              antiek_status: "behind",
                                              residual: "p",
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
                                          quality_floor: 0.5,
                                          would_exceed: false,
                                        },
                                        nd_weekly: {
                                          nd_shadow: {
                                            selected_model_id: "gpt-5",
                                            kill_switch_on: true,
                                            inventory_model_ids: ["gpt-5"],
                                            task: "deep_research",
                                          },
                                          weekly_market: {
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
                                            market_research: {
                                              market: {
                                                title: "S",
                                                account_id: "a",
                                                free_copy_available: true,
                                                free_html_projection_sha:
                                                  "sha",
                                                purchase_ack: false,
                                                port_requested: true,
                                              },
                                              research: {
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
                                                      title: "E",
                                                      external_id:
                                                        "substack:x",
                                                      url: "https://example.substack.com/p/x",
                                                      html_fragment:
                                                        "<article>e</article>",
                                                    },
                                                  ],
                                                  quality_overall: 0.85,
                                                  quality_floor: 0.7,
                                                  would_exceed: false,
                                                },
                                                record_html: {
                                                  record_prompt: {
                                                    session_id: "sess-demo",
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
                                                        body: "g?",
                                                      },
                                                    ],
                                                    user_prompt: "S",
                                                    selected_model_id: "gpt-5",
                                                    models: [
                                                      {
                                                        model_id: "gpt-5",
                                                        projected_cost_usd_high: 2,
                                                      },
                                                    ],
                                                    daily_cap_usd: 100,
                                                    spent_usd: 40,
                                                    projected_cost_usd_high: 2,
                                                  },
                                                  html_pack: {
                                                    html_view: {
                                                      session_id: "sess-demo",
                                                      asset_id: "book-demo",
                                                      html_projection_sha:
                                                        "sha",
                                                      view_requested: true,
                                                      twin_bound: true,
                                                      twin_substrate_ready:
                                                        true,
                                                      claimed_format: "html",
                                                    },
                                                    twin_mo: {
                                                      twin: {
                                                        parent_asset_id:
                                                          "book-demo",
                                                        source_excerpt:
                                                          "<p>x</p>",
                                                        focus_questions: ["?"],
                                                      },
                                                      mo_write: {
                                                        mo: {
                                                          operator_id: "op",
                                                          work_minutes: 60,
                                                          goals: [
                                                            {
                                                              goal_id: "g1",
                                                              title: "A",
                                                            },
                                                            {
                                                              goal_id: "g2",
                                                              title: "B",
                                                            },
                                                          ],
                                                          usd_per_hour: 30,
                                                          price_ceiling_ack:
                                                            true,
                                                          stage:
                                                            "recommend_only",
                                                        },
                                                        research_write: {
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
                                                                insights: [
                                                                  "h",
                                                                ],
                                                                questions: [
                                                                  "q",
                                                                ],
                                                              },
                                                            ],
                                                            chase_slots: [
                                                              {
                                                                slot_id: "s1",
                                                                question_id:
                                                                  "q1",
                                                                parent_asset_id:
                                                                  "book-demo",
                                                                status:
                                                                  "completed",
                                                                findings: [
                                                                  "A",
                                                                ],
                                                                body: "E?",
                                                              },
                                                              {
                                                                slot_id: "s2",
                                                                question_id:
                                                                  "q2",
                                                                parent_asset_id:
                                                                  "book-demo",
                                                                status:
                                                                  "completed",
                                                                findings: [
                                                                  "B",
                                                                ],
                                                                body: "C?",
                                                              },
                                                            ],
                                                            analysis_kind:
                                                              "draft_analysis",
                                                          },
                                                          settings_research: {
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
                                                            research_pack: {
                                                              draft_gate: {
                                                                session_id:
                                                                  "sess-demo",
                                                                parent_asset_id:
                                                                  "book-demo",
                                                                sources: [
                                                                  {
                                                                    instance_id:
                                                                      "f1",
                                                                    parent_asset_id:
                                                                      "book-demo",
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
                                                              fullscreen_pack: {
                                                                fullscreen: {
                                                                  session_id:
                                                                    "sess-demo",
                                                                  parent_asset_id:
                                                                    "book-demo",
                                                                  highlight:
                                                                    "c",
                                                                  gated: false,
                                                                },
                                                                weekly_nd: {
                                                                  weekly_learn:
                                                                    {
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
                                                                  nd_research: {
                                                                    nd_shadow: {
                                                                      selected_model_id:
                                                                        "gpt-5.5",
                                                                      kill_switch_on:
                                                                        true,
                                                                      inventory_model_ids:
                                                                        [
                                                                          "gpt-5.5",
                                                                        ],
                                                                      task: "deep_research",
                                                                    },
                                                                    research_pack:
                                                                      {
                                                                        multiselect:
                                                                          {
                                                                            session_id:
                                                                              "sess-demo",
                                                                            parent_asset_id:
                                                                              "book-demo",
                                                                            members:
                                                                              [
                                                                                {
                                                                                  instance_id:
                                                                                    "a",
                                                                                  parent_asset_id:
                                                                                    "book-demo",
                                                                                  status:
                                                                                    "open",
                                                                                  highlight:
                                                                                    "a",
                                                                                },
                                                                                {
                                                                                  instance_id:
                                                                                    "b",
                                                                                  parent_asset_id:
                                                                                    "book-demo",
                                                                                  status:
                                                                                    "completed",
                                                                                  highlight:
                                                                                    "b",
                                                                                  findings:
                                                                                    [
                                                                                      "f",
                                                                                    ],
                                                                                },
                                                                              ],
                                                                            selected_instance_ids:
                                                                              [
                                                                                "a",
                                                                                "b",
                                                                              ],
                                                                            pack_mode:
                                                                              "cohesive_prompt",
                                                                            cohesive_prompt:
                                                                              "S",
                                                                          },
                                                                        workstation_marketplace:
                                                                          {
                                                                            records:
                                                                              {
                                                                                session_id:
                                                                                  "sess-demo",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                records:
                                                                                  [
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
                                                                                mark_for_prompt_context:
                                                                                  true,
                                                                              },
                                                                            marketplace_research:
                                                                              {
                                                                                market:
                                                                                  {
                                                                                    session_id:
                                                                                      "sess-demo",
                                                                                    asset_id:
                                                                                      "book-demo",
                                                                                    title:
                                                                                      "S",
                                                                                    account_id:
                                                                                      "a",
                                                                                    free_copy_available:
                                                                                      true,
                                                                                    free_html_projection_sha:
                                                                                      "sha",
                                                                                    port_requested:
                                                                                      true,
                                                                                    purchase_ack:
                                                                                      false,
                                                                                    view_requested:
                                                                                      true,
                                                                                  },
                                                                                research:
                                                                                  {
                                                                                    highlight_surface:
                                                                                      {
                                                                                        highlight:
                                                                                          "n",
                                                                                        gated:
                                                                                          false,
                                                                                        surface_action:
                                                                                          "spawn_only",
                                                                                        source_families:
                                                                                          [
                                                                                            "arxiv",
                                                                                          ],
                                                                                      },
                                                                                    mo_competition:
                                                                                      {
                                                                                        mo: {
                                                                                          operator_id:
                                                                                            "op",
                                                                                          work_minutes: 60,
                                                                                          goals:
                                                                                            [
                                                                                              {
                                                                                                goal_id:
                                                                                                  "g1",
                                                                                                title:
                                                                                                  "S",
                                                                                              },
                                                                                              {
                                                                                                goal_id:
                                                                                                  "g2",
                                                                                                title:
                                                                                                  "T",
                                                                                              },
                                                                                            ],
                                                                                          unattended_ack:
                                                                                            true,
                                                                                          spend_consent:
                                                                                            true,
                                                                                          approved_ceiling_usd: 20,
                                                                                        },
                                                                                        research:
                                                                                          {
                                                                                            decision:
                                                                                              {
                                                                                                selected_model_id:
                                                                                                  "gpt-5.5",
                                                                                                models:
                                                                                                  [
                                                                                                    {
                                                                                                      model_id:
                                                                                                        "gpt-5.5",
                                                                                                    },
                                                                                                  ],
                                                                                                daily_cap_usd: 50,
                                                                                                spent_usd: 5,
                                                                                              },
                                                                                            competition_view:
                                                                                              {
                                                                                                session_id:
                                                                                                  "sess-demo",
                                                                                                asset_id:
                                                                                                  "book-demo",
                                                                                                html_projection_sha:
                                                                                                  "sha",
                                                                                                view_requested:
                                                                                                  true,
                                                                                                twin_bound:
                                                                                                  true,
                                                                                                claimed_format:
                                                                                                  "html",
                                                                                                competition:
                                                                                                  {
                                                                                                    draft_id:
                                                                                                      "d1",
                                                                                                    parent_asset_id:
                                                                                                      "book-demo",
                                                                                                    competitor_decisions:
                                                                                                      [
                                                                                                        {
                                                                                                          competitor:
                                                                                                            "Perplexity",
                                                                                                          area: "citation_grounding",
                                                                                                          decision_summary:
                                                                                                            "c",
                                                                                                          antiek_status:
                                                                                                            "parity",
                                                                                                        },
                                                                                                        {
                                                                                                          competitor:
                                                                                                            "OpenAI DR",
                                                                                                          area: "multi_agent_orchestration",
                                                                                                          decision_summary:
                                                                                                            "a",
                                                                                                          antiek_status:
                                                                                                            "behind",
                                                                                                          residual:
                                                                                                            "p",
                                                                                                        },
                                                                                                      ],
                                                                                                    requested_families:
                                                                                                      [
                                                                                                        "arxiv",
                                                                                                        "substack",
                                                                                                      ],
                                                                                                    citations:
                                                                                                      [
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
                                                                                                    would_exceed:
                                                                                                      false,
                                                                                                    search_query:
                                                                                                      "s",
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
    <div data-testid="source-attach-model-decision-twin-search-panel">
      <LemonCard title="Research · source attach + model decision twin search">
        <p className="text-sm opacity-80">
          HTML-native arxiv/substack attach over model decision budget pack +
          twin search weekly. Pure — no remote fetch, no live route.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
          />
          operator_ack
        </label>
        <LemonButton type="primary" onClick={onCompose} className="mt-2">
          Compose pack
        </LemonButton>
        {error && <p className="text-sm text-danger">{error}</p>}
        {result && (
          <pre className="text-xs mt-2 p-2 bg-bg-light rounded overflow-auto max-h-64">
            {formatSourceAttachModelDecisionTwinSearchSummary(result)}
          </pre>
        )}
      </LemonCard>
    </div>
  );
}
