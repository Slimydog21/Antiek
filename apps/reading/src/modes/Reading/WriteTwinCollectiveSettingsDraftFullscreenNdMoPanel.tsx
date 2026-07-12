/**
 * WriteTwinCollectiveSettingsDraftFullscreenNdMoPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWriteTwinCollectiveSettingsDraftFullscreenNdMo,
  formatWriteTwinCollectiveSettingsDraftFullscreenNdMoSummary,
  type WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose,
} from "../../api/writeTwinCollectiveSettingsDraftFullscreenNdMoCompose";

export default function WriteTwinCollectiveSettingsDraftFullscreenNdMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose | null>(
      null,
    );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeWriteTwinCollectiveSettingsDraftFullscreenNdMo({
          write: {
            session_id: "sess-demo",
            draft_id: "draft-demo",
            parent_asset_id: "book-demo",
            twin_slices: [
              {
                parent_asset_id: "book-demo",
                insights: ["scaling holds"],
                questions: ["Where does it break?"],
              },
            ],
            base_draft_html: "<p>Opening</p>",
            chase_slots: [
              {
                slot_id: "s1",
                question_id: "q1",
                parent_asset_id: "book-demo",
                status: "completed",
                findings: ["finding A"],
                body: "Evidence?",
              },
              {
                slot_id: "s2",
                question_id: "q2",
                parent_asset_id: "book-demo",
                status: "completed",
                findings: ["finding B"],
                body: "Counter?",
              },
            ],
            analysis_kind: "draft_analysis",
          },
          settings_research: {
            settings: {
              models: [{ model_id: "gpt-5.5", provider: "openai" }],
              pending_add_model_ids: ["mimo-v2"],
              action: "preview",
              daily_cap_usd: 25,
              spent_usd: 4,
              selected_model_id: "gpt-5.5",
            },
            research_pack: {
              draft_gate: {
                session_id: "sess-demo",
                parent_asset_id: "book-demo",
                sources: [
                  {
                    instance_id: "float-1",
                    parent_asset_id: "book-demo",
                    status: "completed",
                    findings: ["evidence A"],
                  },
                ],
                stage: "draft_only",
              },
              fullscreen_pack: {
                fullscreen: {
                  session_id: "sess-demo",
                  parent_asset_id: "book-demo",
                  highlight: "Scaling claim",
                  gated: false,
                },
                weekly_nd: {
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
                  nd_research: {
                    nd_shadow: {
                      selected_model_id: "gpt-5.5",
                      kill_switch_on: true,
                      inventory_model_ids: ["gpt-5.5"],
                      task: "deep_research",
                    },
                    research_pack: {
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
                        cohesive_prompt: "Synthesize",
                      },
                      workstation_marketplace: {
                        records: {
                          session_id: "sess-demo",
                          parent_asset_id: "book-demo",
                          records: [
                            {
                              record_id: "r1",
                              kind: "insight",
                              body: "holds",
                            },
                            {
                              record_id: "r2",
                              kind: "question",
                              body: "gaps?",
                            },
                          ],
                          mark_for_prompt_context: true,
                        },
                        marketplace_research: {
                          market: {
                            session_id: "sess-demo",
                            asset_id: "book-demo",
                            title: "Scaling",
                            account_id: "acct",
                            free_copy_available: true,
                            free_html_projection_sha: "sha",
                            port_requested: true,
                            purchase_ack: false,
                            view_requested: true,
                          },
                          research: {
                            highlight_surface: {
                              highlight: "noise",
                              gated: false,
                              surface_action: "spawn_only",
                              source_families: ["arxiv"],
                            },
                            mo_competition: {
                              mo: {
                                operator_id: "op",
                                work_minutes: 60,
                                goals: [
                                  { goal_id: "g1", title: "Survey" },
                                  { goal_id: "g2", title: "Twin" },
                                ],
                                unattended_ack: true,
                                spend_consent: true,
                                approved_ceiling_usd: 20,
                              },
                              research: {
                                decision: {
                                  selected_model_id: "gpt-5.5",
                                  models: [{ model_id: "gpt-5.5" }],
                                  daily_cap_usd: 50,
                                  spent_usd: 5,
                                },
                                competition_view: {
                                  session_id: "sess-demo",
                                  asset_id: "book-demo",
                                  html_projection_sha: "sha",
                                  view_requested: true,
                                  twin_bound: true,
                                  claimed_format: "html",
                                  competition: {
                                    draft_id: "d1",
                                    parent_asset_id: "book-demo",
                                    competitor_decisions: [
                                      {
                                        competitor: "Perplexity",
                                        area: "citation_grounding",
                                        decision_summary: "cites",
                                        antiek_status: "parity",
                                      },
                                      {
                                        competitor: "OpenAI DR",
                                        area: "multi_agent_orchestration",
                                        decision_summary: "agents",
                                        antiek_status: "behind",
                                        residual: "cohesive pack",
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
    <div data-testid="write-twin-collective-settings-draft-fullscreen-nd-mo-panel">
      <LemonCard title="Write · twin collective + settings draft fullscreen ND">
        <p className="text-sm opacity-80">
          Merge chase findings into written analysis over settings+draft
          fullscreen weekly ND pack. Pure — never writes.
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
            {formatWriteTwinCollectiveSettingsDraftFullscreenNdMoSummary(
              result,
            )}
          </pre>
        )}
      </LemonCard>
    </div>
  );
}
