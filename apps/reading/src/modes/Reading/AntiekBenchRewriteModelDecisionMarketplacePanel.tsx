/**
 * AntiekBenchRewriteModelDecisionMarketplacePanel — free-file.
 * Antiek-bench recursive rewrite residual over model decision + twin search
 * HTML-native recursive twin marketplace pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeAntiekBenchRewriteModelDecisionMarketplace,
  formatAntiekBenchRewriteModelDecisionMarketplaceSummary,
  type AntiekBenchRewriteModelDecisionMarketplaceCompose,
} from "../../api/antiekBenchRewriteModelDecisionMarketplaceCompose";

export default function AntiekBenchRewriteModelDecisionMarketplacePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchRewriteModelDecisionMarketplaceCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      // Compact demo — full nest proven in pure tests.
      setResult(
        composeAntiekBenchRewriteModelDecisionMarketplace({
          rewrite: {
            week_label: "2026-W28",
            patterns: [
              {
                task_family: "deep_research",
                model_id: "gpt-5",
                outcome: "failed",
                n: 3,
              },
              {
                task_family: "twin_notes",
                model_id: "claude",
                outcome: "worked",
                n: 2,
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
              search_query: "scaling noise",
              twin_records: [
                {
                  twin_id: "twin-book-demo",
                  parent_asset_id: "book-demo",
                  insights: ["scaling laws hold under noise"],
                  questions: ["Where does it break?"],
                },
              ],
              html_pack: {
                html_view: {
                  session_id: "sess-demo",
                  asset_id: "book-demo",
                  html_projection_sha: "sha-html-ready",
                  view_requested: true,
                  twin_bound: true,
                  twin_substrate_ready: true,
                  claimed_format: "html",
                },
                twin_pack: {
                  twin: {
                    parent_asset_id: "book-demo",
                    source_excerpt: "<p>Scaling laws hold under noise.</p>",
                    focus_questions: ["Where does it break?"],
                    existing_twin_asset_id: "twin-book-demo",
                  },
                  market_pack: {
                    market: {
                      title: "Scaling Laws Book",
                      account_id: "acct-demo",
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
                        quality_overall: 0.85,
                        quality_floor: 0.5,
                        would_exceed: false,
                      },
                      settings_pack: {
                        settings: {
                          models: [
                            { model_id: "gpt-5.5", provider: "openai" },
                          ],
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
                                  title: "Scaling Laws",
                                  external_id: "arxiv:1",
                                  html_fragment: "<article>a</article>",
                                },
                                {
                                  source_id: "sub-1",
                                  family: "substack",
                                  title: "Notes",
                                  external_id: "substack:n",
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
                                    {
                                      goal_id: "g1",
                                      title: "Map arxiv competition gaps",
                                    },
                                    {
                                      goal_id: "g2",
                                      title: "Synthesize twin notes",
                                    },
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
                                    highlight: "Scaling claim",
                                    prompt: "Evidence?",
                                    gated: false,
                                  },
                                  draft_collective: {
                                    draft_gate: {
                                      session_id: "sess-demo",
                                      parent_asset_id: "book-demo",
                                      parent_excerpt: "<p>Parent</p>",
                                      sources: [
                                        {
                                          instance_id: "float-1",
                                          parent_asset_id: "book-demo",
                                          status: "completed",
                                          highlight: "key claim",
                                          findings: ["evidence A"],
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
                                            instance_id: "inst-a",
                                            parent_asset_id: "book-demo",
                                            status: "open",
                                            highlight: "claim",
                                          },
                                          {
                                            instance_id: "inst-b",
                                            parent_asset_id: "book-demo",
                                            status: "completed",
                                            highlight: "counter",
                                            findings: ["b1"],
                                          },
                                        ],
                                        selected_instance_ids: [
                                          "inst-a",
                                          "inst-b",
                                        ],
                                        pack_mode: "cohesive_prompt",
                                        cohesive_prompt: "Synthesize A and B",
                                      },
                                      paid_nd: {
                                        purchase: {
                                          title: "Scaling Laws Book",
                                          account_id: "acct-demo",
                                          free_copy_available: true,
                                          free_html_projection_sha: "sha-free",
                                          purchase_ack: false,
                                          port_requested: true,
                                          list_price_usd: 10,
                                          approved_spend_usd: 20,
                                          remaining_budget_usd: 50,
                                        },
                                        nd_twin: {
                                          nd_shadow: {
                                            selected_model_id: "gpt-5.5",
                                            nd_recommended_model_id:
                                              "claude-opus",
                                            kill_switch_on: true,
                                            confidence: 0.72,
                                            task: "deep_research",
                                            inventory_model_ids: [
                                              "gpt-5.5",
                                              "claude-opus",
                                            ],
                                          },
                                          twin_presentation: {
                                            twin: {
                                              parent_asset_id: "book-demo",
                                              source_excerpt:
                                                "<p>Scaling laws.</p>",
                                              focus_questions: [
                                                "Where does it break?",
                                              ],
                                              existing_twin_asset_id:
                                                "twin-book-demo",
                                            },
                                            presentation: {
                                              view_mode: "side_panel",
                                              open_requested: true,
                                              merge_to_parent_preview: false,
                                              presented_insights: [
                                                "scaling holds",
                                              ],
                                              presented_questions: [
                                                "Where does it break?",
                                              ],
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
                                                quality_overall: 0.85,
                                                quality_floor: 0.5,
                                                would_exceed: false,
                                              },
                                              free_pack: {
                                                market: {
                                                  title: "Scaling Laws Book",
                                                  account_id: "acct-demo",
                                                  free_copy_available: true,
                                                  free_html_projection_sha:
                                                    "sha-free",
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
                                                        {
                                                          goal_id: "g1",
                                                          title: "Map gaps",
                                                        },
                                                        {
                                                          goal_id: "g2",
                                                          title: "Twin notes",
                                                        },
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
                                                        parent_asset_id:
                                                          "book-demo",
                                                        requested_families: [
                                                          "arxiv",
                                                          "substack",
                                                        ],
                                                        sources: [
                                                          {
                                                            source_id: "arx-1",
                                                            family: "arxiv",
                                                            title: "S",
                                                            external_id:
                                                              "arxiv:1",
                                                            html_fragment:
                                                              "<article>a</article>",
                                                          },
                                                          {
                                                            source_id: "sub-1",
                                                            family: "substack",
                                                            title: "N",
                                                            external_id:
                                                              "substack:n",
                                                            url: "https://example.substack.com/p/n",
                                                            html_fragment:
                                                              "<article>b</article>",
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
                                                              projected_cost_usd_low: 1,
                                                            },
                                                          ],
                                                          daily_cap_usd: 50,
                                                          spent_usd: 10,
                                                          projected_cost_usd_high: 2,
                                                          projected_cost_usd_low: 1,
                                                          focus_task:
                                                            "deep_research",
                                                        },
                                                        twin_search_pack: {
                                                          search_query:
                                                            "scaling noise",
                                                          twin_records: [
                                                            {
                                                              twin_id:
                                                                "twin-book-demo",
                                                              parent_asset_id:
                                                                "book-demo",
                                                              insights: [
                                                                "scaling holds",
                                                              ],
                                                              questions: [
                                                                "break?",
                                                              ],
                                                            },
                                                          ],
                                                          weekly_html: {
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
                                                            html_pack: {
                                                              html_view: {
                                                                session_id:
                                                                  "sess-demo",
                                                                asset_id:
                                                                  "book-demo",
                                                                html_projection_sha:
                                                                  "sha-html-ready",
                                                                view_requested: true,
                                                                twin_bound: true,
                                                                twin_substrate_ready: true,
                                                                claimed_format:
                                                                  "html",
                                                              },
                                                              twin_pack: {
                                                                twin: {
                                                                  parent_asset_id:
                                                                    "book-demo",
                                                                  source_excerpt:
                                                                    "<p>Scaling.</p>",
                                                                  focus_questions: [
                                                                    "break?",
                                                                  ],
                                                                },
                                                                settings_pack: {
                                                                  settings: {
                                                                    models: [
                                                                      {
                                                                        model_id:
                                                                          "gpt-5.5",
                                                                        provider:
                                                                          "openai",
                                                                      },
                                                                    ],
                                                                    pending_add_model_ids: [
                                                                      "mimo-v2",
                                                                    ],
                                                                    action:
                                                                      "preview",
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
                                                                      highlight:
                                                                        "claim",
                                                                      prompt:
                                                                        "Evidence?",
                                                                      gated: false,
                                                                    },
                                                                    mo_pack: {
                                                                      mo: {
                                                                        operator_id:
                                                                          "op-1",
                                                                        work_minutes: 120,
                                                                        goals: [
                                                                          {
                                                                            goal_id:
                                                                              "g1",
                                                                            title:
                                                                              "Map",
                                                                          },
                                                                          {
                                                                            goal_id:
                                                                              "g2",
                                                                            title:
                                                                              "Synthesize",
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
                                                                            "sess-demo",
                                                                          parent_asset_id:
                                                                            "book-demo",
                                                                          parent_excerpt:
                                                                            "<p>P</p>",
                                                                          sources: [
                                                                            {
                                                                              instance_id:
                                                                                "float-1",
                                                                              parent_asset_id:
                                                                                "book-demo",
                                                                              status:
                                                                                "completed",
                                                                              highlight:
                                                                                "key",
                                                                              findings: [
                                                                                "A",
                                                                              ],
                                                                            },
                                                                          ],
                                                                          stage:
                                                                            "draft_only",
                                                                        },
                                                                        multi_pack: {
                                                                          multiselect: {
                                                                            session_id:
                                                                              "sess-demo",
                                                                            parent_asset_id:
                                                                              "book-demo",
                                                                            members: [
                                                                              {
                                                                                instance_id:
                                                                                  "inst-a",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                status:
                                                                                  "open",
                                                                                highlight:
                                                                                  "a",
                                                                              },
                                                                              {
                                                                                instance_id:
                                                                                  "inst-b",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                status:
                                                                                  "completed",
                                                                                highlight:
                                                                                  "b",
                                                                                findings: [
                                                                                  "b1",
                                                                                ],
                                                                              },
                                                                            ],
                                                                            selected_instance_ids: [
                                                                              "inst-a",
                                                                              "inst-b",
                                                                            ],
                                                                            pack_mode:
                                                                              "cohesive_prompt",
                                                                            cohesive_prompt:
                                                                              "Synthesize",
                                                                          },
                                                                          record_write: {
                                                                            record_prompt: {
                                                                              session_id:
                                                                                "sess-demo",
                                                                              parent_asset_id:
                                                                                "book-demo",
                                                                              records: [
                                                                                {
                                                                                  record_id:
                                                                                    "r1",
                                                                                  kind: "insight",
                                                                                  body: "holds",
                                                                                },
                                                                                {
                                                                                  record_id:
                                                                                    "r2",
                                                                                  kind: "question",
                                                                                  body: "break?",
                                                                                },
                                                                              ],
                                                                              user_prompt:
                                                                                "Summarize",
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
                                                                                draft_id:
                                                                                  "draft-1",
                                                                                parent_asset_id:
                                                                                  "book-demo",
                                                                                twin_slices: [
                                                                                  {
                                                                                    parent_asset_id:
                                                                                      "a1",
                                                                                    insights: [
                                                                                      "holds",
                                                                                    ],
                                                                                    questions: [
                                                                                      "break?",
                                                                                    ],
                                                                                  },
                                                                                  {
                                                                                    parent_asset_id:
                                                                                      "a2",
                                                                                    insights: [
                                                                                      "attn",
                                                                                    ],
                                                                                    questions: [],
                                                                                  },
                                                                                ],
                                                                                base_draft_html:
                                                                                  "<p>Open</p>",
                                                                                chase_slots: [
                                                                                  {
                                                                                    slot_id:
                                                                                      "s1",
                                                                                    question_id:
                                                                                      "q1",
                                                                                    parent_asset_id:
                                                                                      "book-demo",
                                                                                    status:
                                                                                      "completed",
                                                                                    findings: [
                                                                                      "A",
                                                                                    ],
                                                                                    body: "Evidence?",
                                                                                  },
                                                                                  {
                                                                                    slot_id:
                                                                                      "s2",
                                                                                    question_id:
                                                                                      "q2",
                                                                                    parent_asset_id:
                                                                                      "book-demo",
                                                                                    status:
                                                                                      "completed",
                                                                                    findings: [
                                                                                      "B",
                                                                                    ],
                                                                                    body: "Counter?",
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
        Antiek-bench rewrite · model decision marketplace
      </h2>
      <p className="text-sm text-muted">
        Pure residual: recursive rewrite proposals over model decision budget +
        twin search HTML-native marketplace. suite_rewritten=false ·
        applied=false · live_router_authorized=false · ND REJECT.
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
        Compose rewrite residual pack
      </LemonButton>
      {error && (
        <LemonCard className="border-danger p-3 text-sm text-danger">
          {error}
        </LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm space-y-1">
          <div>
            {formatAntiekBenchRewriteModelDecisionMarketplaceSummary(result)}
          </div>
          <div>pack_ready={String(result.pack_ready)}</div>
          <div>proposal_count={result.proposal_count}</div>
          <div>suite_rewritten={String(result.suite_rewritten)}</div>
          <div>applied={String(result.applied)}</div>
          <div>
            production_router_verdict={result.production_router_verdict}
          </div>
          <div className="text-xs text-muted max-h-40 overflow-auto">
            {result.notes.slice(0, 12).join(" · ")}
          </div>
        </LemonCard>
      )}
    </div>
  );
}
