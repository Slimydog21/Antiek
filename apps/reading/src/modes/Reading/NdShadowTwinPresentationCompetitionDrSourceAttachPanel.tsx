/**
 * NdShadowTwinPresentationCompetitionDrSourceAttachPanel — free-file.
 * Twin note-taker presentation (side-panel/overlay/fullscreen/inline)
 * over competition DR quality + source-attach Antiek-bench recommend pack.
 * Pure advisory only — twin_written/merge_executed always false.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeNdShadowTwinPresentationCompetitionDrSourceAttach,
  formatNdShadowTwinPresentationCompetitionDrSourceAttachSummary,
  type NdShadowTwinPresentationCompetitionDrSourceAttachCompose,
  type TwinPresentationViewMode,
} from "../../api/ndShadowTwinPresentationCompetitionDrSourceAttachCompose";

const VIEW_MODES: TwinPresentationViewMode[] = [
  "side_panel",
  "overlay",
  "fullscreen_twin",
  "inline",
];

export default function NdShadowTwinPresentationCompetitionDrSourceAttachPanel() {
  const [ack, setAck] = useState(true);
  const [openRequested, setOpenRequested] = useState(true);
  const [viewMode, setViewMode] =
    useState<TwinPresentationViewMode>("side_panel");
  const [mergePreview, setMergePreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NdShadowTwinPresentationCompetitionDrSourceAttachCompose | null>(
      null,
    );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      // Compact demo fixtures — full nest proven in pure tests.
      setResult(
        composeNdShadowTwinPresentationCompetitionDrSourceAttach({
          nd_shadow: {
            selected_model_id: "gpt-5.5",
            nd_recommended_model_id: "claude-opus",
            kill_switch_on: true,
            confidence: 0.72,
            task: "deep_research",
            inventory_model_ids: ["gpt-5.5", "claude-opus", "mimo"],
          },
          twin_presentation: {
          twin: {
            parent_asset_id: "book-demo",
            source_excerpt:
              "<p>Scaling laws hold under noise in compute-optimal regimes.</p>",
            focus_questions: [
              "Where does it break?",
              "What residual gaps remain?",
            ],
            existing_twin_asset_id: "twin-book-demo",
          },
          presentation: {
            view_mode: viewMode,
            open_requested: openRequested,
            merge_to_parent_preview: mergePreview,
            presented_insights: [
              "scaling laws hold under noise in compute-optimal regimes",
            ],
            presented_questions: [
              "Where does scaling break under distribution shift?",
            ],
          },
          competition_pack: {
            competition: {
              session_id: "sess-demo",
              competitor_decisions: [
                {
                  competitor: "Perplexity",
                  area: "citation_grounding",
                  decision_summary: "Inline citations",
                  antiek_status: "parity",
                },
                {
                  competitor: "OpenAI DR",
                  area: "multi_agent_orchestration",
                  decision_summary: "Planner agents",
                  antiek_status: "behind",
                  residual: "pack cohesion",
                },
              ],
              requested_families: ["arxiv", "substack"],
              citations: [
                {
                  citation_id: "c1",
                  family: "arxiv",
                  title: "Scaling",
                  external_id: "arxiv:1",
                },
                {
                  citation_id: "c2",
                  family: "substack",
                  title: "Notes",
                  url: "https://example.substack.com/p/n",
                },
              ],
              quality_overall: 0.8,
              quality_floor: 0.5,
              would_exceed: false,
            },
            source_pack: {
              sources: {
                session_id: "sess-demo",
                parent_asset_id: "book-demo",
                requested_families: ["arxiv", "substack"],
                sources: [
                  {
                    source_id: "s1",
                    family: "arxiv",
                    title: "Scaling Laws",
                    external_id: "arxiv:1",
                    html_fragment: "<article>a</article>",
                  },
                  {
                    source_id: "s2",
                    family: "substack",
                    title: "Notes",
                    external_id: "substack:n",
                    url: "https://example.substack.com/p/n",
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
                    { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
                    { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
                  ],
                  daily_cap_usd: 20,
                  spent_usd: 5,
                  projected_cost_usd_high: 0.5,
                  existing_tasks: ["deep_research"],
                },
                mo_pack: {
                  mo: {
                    operator_id: "op-demo",
                    work_minutes: 120,
                    goals: [
                      { goal_id: "g1", title: "Map arxiv gaps" },
                      { goal_id: "g2", title: "Synth twin notes" },
                    ],
                    usd_per_hour: 15,
                    approved_ceiling_usd: 50,
                    unattended_ack: true,
                    spend_consent: true,
                  },
                  fullscreen_pack: {
                    fullscreen: {
                      session_id: "sess-demo",
                      parent_asset_id: "book-demo",
                      highlight: "scaling residual",
                      gated: false,
                    },
                    draft_pack: {
                      draft_gate: {
                        session_id: "sess-demo",
                        parent_asset_id: "book-demo",
                        sources: [
                          {
                            instance_id: "a",
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
                              market_pack: {
                                market: {
                                  title: "Scaling Laws Book",
                                  account_id: "acct-demo",
                                  free_copy_available: true,
                                  free_html_projection_sha: "sha-free",
                                  purchase_ack: false,
                                  port_requested: true,
                                },
                                settings_pack: {
                                  settings: {
                                    models: [{ model_id: "gpt-5.5" }],
                                    action: "preview",
                                    daily_cap_usd: 25,
                                    spent_usd: 4,
                                    selected_model_id: "gpt-5.5",
                                  },
                                  nd_pack: {
                                    nd_shadow: {
                                      selected_model_id: "gpt-5.5",
                                      nd_recommended_model_id: "claude-opus",
                                      kill_switch_on: true,
                                      inventory_model_ids: [
                                        "gpt-5.5",
                                        "claude-opus",
                                      ],
                                      task: "deep_research",
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
                                        quality_overall: 0.8,
                                        would_exceed: false,
                                      },
                                      mo_pack: {
                                        mo: {
                                          operator_id: "op-demo",
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
                                                title: "Scaling",
                                                external_id: "arxiv:1",
                                                html_fragment:
                                                  "<article>a</article>",
                                              },
                                              {
                                                source_id: "sub-1",
                                                family: "substack",
                                                title: "Notes",
                                                url: "https://example.substack.com/p/n",
                                                html_fragment:
                                                  "<article>e</article>",
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
                                            },
                                            twin_search_pack: {
                                              search_query: "scaling",
                                              twin_records: [
                                                {
                                                  twin_id: "t1",
                                                  parent_asset_id: "book-demo",
                                                  insights: ["i"],
                                                  questions: ["q"],
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
                                                      source_excerpt: "<p>x</p>",
                                                      focus_questions: ["?"],
                                                    },
                                                    settings_pack: {
                                                      settings: {
                                                        models: [
                                                          {
                                                            model_id: "gpt-5.5",
                                                          },
                                                        ],
                                                        action: "preview",
                                                        daily_cap_usd: 25,
                                                        spent_usd: 4,
                                                        selected_model_id:
                                                          "gpt-5.5",
                                                      },
                                                      fullscreen_mo: {
                                                        fullscreen: {
                                                          session_id:
                                                            "sess-demo",
                                                          parent_asset_id:
                                                            "book-demo",
                                                          highlight: "c",
                                                          gated: false,
                                                        },
                                                        mo_pack: {
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
                                                          draft_multi: {
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
                                                            multi_pack: {
                                                              multiselect: {
                                                                session_id:
                                                                  "sess-demo",
                                                                parent_asset_id:
                                                                  "book-demo",
                                                                members: [
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
                                                                    findings: [
                                                                      "f",
                                                                    ],
                                                                  },
                                                                ],
                                                                selected_instance_ids:
                                                                  ["a", "b"],
                                                                pack_mode:
                                                                  "cohesive_prompt",
                                                                cohesive_prompt:
                                                                  "S",
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
                                                                      "sess-demo",
                                                                    draft_id:
                                                                      "d1",
                                                                    parent_asset_id:
                                                                      "book-demo",
                                                                    twin_slices:
                                                                      [
                                                                        {
                                                                          parent_asset_id:
                                                                            "a1",
                                                                          insights:
                                                                            [
                                                                              "i",
                                                                            ],
                                                                          questions:
                                                                            [
                                                                              "q",
                                                                            ],
                                                                        },
                                                                        {
                                                                          parent_asset_id:
                                                                            "a2",
                                                                          insights:
                                                                            [
                                                                              "j",
                                                                            ],
                                                                          questions:
                                                                            [],
                                                                        },
                                                                      ],
                                                                    chase_slots:
                                                                      [
                                                                        {
                                                                          slot_id:
                                                                            "s1",
                                                                          question_id:
                                                                            "q1",
                                                                          parent_asset_id:
                                                                            "book-demo",
                                                                          status:
                                                                            "completed",
                                                                          findings:
                                                                            [
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
                                                                            "book-demo",
                                                                          status:
                                                                            "completed",
                                                                          findings:
                                                                            [
                                                                              "f2",
                                                                            ],
                                                                          body: "?",
                                                                        },
                                                                      ],
                                                                    analysis_kind:
                                                                      "draft_analysis",
                                                                  },
                                                                  highlight_pack:
                                                                    {
                                                                      highlight:
                                                                        {
                                                                          parent_asset_id:
                                                                            "book-demo",
                                                                          highlight:
                                                                            "scaling residual",
                                                                          gated: false,
                                                                          would_exceed: false,
                                                                          preferred_view_mode:
                                                                            "floating",
                                                                          source_families:
                                                                            [
                                                                              "arxiv",
                                                                              "substack",
                                                                            ],
                                                                        },
                                                                      twin_search_pack:
                                                                        {
                                                                          competition_pack:
                                                                            {
                                                                              competition:
                                                                                {
                                                                                  session_id:
                                                                                    "sess-demo",
                                                                                  competitor_decisions:
                                                                                    [
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
                                                                                  would_exceed: false,
                                                                                  search_query:
                                                                                    "scaling",
                                                                                },
                                                                              nd_weekly:
                                                                                {
                                                                                  nd_shadow:
                                                                                    {
                                                                                      selected_model_id:
                                                                                        "gpt-5.5",
                                                                                      nd_recommended_model_id:
                                                                                        "claude-opus",
                                                                                      kill_switch_on: true,
                                                                                      inventory_model_ids:
                                                                                        [
                                                                                          "gpt-5.5",
                                                                                          "claude-opus",
                                                                                        ],
                                                                                      task: "deep_research",
                                                                                    },
                                                                                  weekly_market:
                                                                                    {
                                                                                      weekly_learn:
                                                                                        {
                                                                                          week_id:
                                                                                            "2026-W28",
                                                                                          min_events_per_task: 2,
                                                                                          events:
                                                                                            [
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
                                                                                      market_research:
                                                                                        {
                                                                                          market:
                                                                                            {
                                                                                              session_id:
                                                                                                "sess-demo",
                                                                                              asset_id:
                                                                                                "book-demo",
                                                                                              title:
                                                                                                "Scaling Laws",
                                                                                              account_id:
                                                                                                "acct-demo",
                                                                                              free_copy_available: true,
                                                                                              free_html_projection_sha:
                                                                                                "sha-free",
                                                                                              port_requested: true,
                                                                                              purchase_ack: false,
                                                                                              list_price_usd: 10,
                                                                                              approved_spend_usd: 20,
                                                                                              remaining_budget_usd: 50,
                                                                                              view_requested: true,
                                                                                            },
                                                                                          research:
                                                                                            {
                                                                                              highlight_surface:
                                                                                                {
                                                                                                  highlight:
                                                                                                    "scaling",
                                                                                                  gated: false,
                                                                                                  would_exceed: false,
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
                                                                                                      "op-demo",
                                                                                                    work_minutes: 120,
                                                                                                    goals:
                                                                                                      [
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
                                                                                                                projected_cost_usd_high: 2,
                                                                                                                projected_cost_usd_low: 1,
                                                                                                              },
                                                                                                            ],
                                                                                                          daily_cap_usd: 50,
                                                                                                          spent_usd: 10,
                                                                                                        },
                                                                                                      competition_view:
                                                                                                        {
                                                                                                          session_id:
                                                                                                            "sess-demo",
                                                                                                          asset_id:
                                                                                                            "book-demo",
                                                                                                          html_projection_sha:
                                                                                                            "sha-free",
                                                                                                          view_requested: true,
                                                                                                          twin_bound: true,
                                                                                                          claimed_format:
                                                                                                            "html",
                                                                                                          competition:
                                                                                                            {
                                                                                                              draft_id:
                                                                                                                "draft-1",
                                                                                                              parent_asset_id:
                                                                                                                "book-demo",
                                                                                                              competitor_decisions:
                                                                                                                [
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
      data-testid="nd-shadow-twin-presentation-competition-dr-source-attach-panel"
    >
      <h2 className="text-lg font-semibold">
        ND shadow REJECT · twin presentation · competition DR source-attach
      </h2>
      <p className="text-sm text-muted">
        Pure advisory — twin_written / merge_executed / purchase_executed always
        false. ND production REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        operator_ack
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={openRequested}
          onChange={(e) => setOpenRequested(e.target.checked)}
        />
        open_requested
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={mergePreview}
          onChange={(e) => setMergePreview(e.target.checked)}
        />
        merge_to_parent_preview (draft only)
      </label>
      <label className="flex flex-col gap-1 text-sm">
        view_mode
        <select
          value={viewMode}
          onChange={(e) =>
            setViewMode(e.target.value as TwinPresentationViewMode)
          }
        >
          {VIEW_MODES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose presentation pack
      </LemonButton>
      {error && (
        <pre className="text-xs text-danger whitespace-pre-wrap">{error}</pre>
      )}
      {result && (
        <div className="space-y-2 text-sm">
          <div data-testid="summary">
            {formatNdShadowTwinPresentationCompetitionDrSourceAttachSummary(
              result,
            )}
          </div>
          <div>
            pack_ready=<strong>{String(result.pack_ready)}</strong> ·
            twin_ready=
            <strong>{String(result.twin_presentation.pack_ready)}</strong> ·
            presentation_ready=
            <strong>
              {String(result.twin_presentation.presentation.presentation_ready)}
            </strong>{" "}
            · view_mode=
            <strong>{result.twin_presentation.presentation.view_mode}</strong>
          </div>
          <div>
            live_router_authorized={String(result.live_router_authorized)} ·
            twin_written={String(result.twin_written)} · merge_executed=
            {String(result.merge_executed)} · purchase_executed=
            {String(result.purchase_executed)} · verdict=
            {result.production_router_verdict}
          </div>
        </div>
      )}
    </LemonCard>
  );
}
