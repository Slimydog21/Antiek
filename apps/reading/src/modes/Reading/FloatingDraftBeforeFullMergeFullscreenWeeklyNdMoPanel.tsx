/**
 * FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoPanel — free-file.
 *
 * Pure advisory panel: draft-before-full-merge over fullscreen weekly ND pack.
 * Never writes, merges, live-dispatches, or mutates bench store.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingDraftBeforeFullMergeFullscreenWeeklyNdMo,
  formatFloatingDraftBeforeFullMergeFullscreenWeeklyNdMoSummary,
  type FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose,
} from "../../api/floatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose";

export default function FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose | null>(
      null,
    );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFloatingDraftBeforeFullMergeFullscreenWeeklyNdMo({
          draft_gate: {
            session_id: "sess-demo",
            parent_asset_id: "book-demo",
            parent_excerpt: "<p>Parent body on scaling laws</p>",
            sources: [
              {
                instance_id: "float-demo",
                parent_asset_id: "book-demo",
                status: "completed",
                highlight: "key claim from float",
                findings: ["evidence A"],
              },
            ],
            stage: "draft_only",
          },
          fullscreen_pack: {
            fullscreen: {
              session_id: "sess-demo",
              parent_asset_id: "book-demo",
              highlight: "Scaling laws claim from page 12",
              prompt: "What evidence supports this?",
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
                  nd_recommended_model_id: "claude-opus",
                  kill_switch_on: true,
                  inventory_model_ids: ["gpt-5.5", "claude-opus"],
                  task: "deep_research",
                },
                research_pack: {
                  multiselect: {
                    session_id: "sess-demo",
                    parent_asset_id: "book-demo",
                    members: [
                      {
                        instance_id: "inst-a",
                        parent_asset_id: "book-demo",
                        status: "open",
                        highlight: "scaling laws claim",
                      },
                      {
                        instance_id: "inst-b",
                        parent_asset_id: "book-demo",
                        status: "completed",
                        highlight: "counter-evidence",
                        findings: ["finding-b1"],
                      },
                    ],
                    selected_instance_ids: ["inst-a", "inst-b"],
                    pack_mode: "cohesive_prompt",
                    cohesive_prompt: "Synthesize A and B as one unit",
                  },
                  workstation_marketplace: {
                    records: {
                      session_id: "sess-demo",
                      parent_asset_id: "book-demo",
                      records: [
                        {
                          record_id: "r1",
                          kind: "insight",
                          body: "Power-law scaling holds",
                        },
                        {
                          record_id: "r2",
                          kind: "question",
                          body: "What residual gaps remain?",
                        },
                      ],
                      mark_for_prompt_context: true,
                    },
                    marketplace_research: {
                      market: {
                        session_id: "sess-demo",
                        asset_id: "book-demo",
                        title: "Scaling Laws",
                        account_id: "acct-demo",
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
                          surface_action: "spawn_only",
                          source_families: ["arxiv"],
                        },
                        mo_competition: {
                          mo: {
                            operator_id: "op-demo",
                            work_minutes: 120,
                            goals: [
                              {
                                goal_id: "g1",
                                title: "Survey arxiv competition gaps",
                              },
                              {
                                goal_id: "g2",
                                title: "Draft twin notes",
                              },
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
                              session_id: "sess-demo",
                              asset_id: "book-demo",
                              html_projection_sha: "sha-free",
                              view_requested: true,
                              twin_bound: true,
                              claimed_format: "html",
                              competition: {
                                draft_id: "draft-demo",
                                parent_asset_id: "book-demo",
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
                                    decision_summary:
                                      "Planner + browser agents",
                                    antiek_status: "behind",
                                    residual:
                                      "strengthen collective floating cohesive pack",
                                  },
                                ],
                                requested_families: ["arxiv", "substack"],
                                citations: [
                                  {
                                    citation_id: "c1",
                                    family: "arxiv",
                                    title: "Scaling Laws under Noise",
                                    external_id: "arxiv:2301.00001",
                                  },
                                  {
                                    citation_id: "c2",
                                    family: "substack",
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
    <div data-testid="floating-draft-before-full-merge-fullscreen-weekly-nd-mo-panel">
      <LemonCard
        title="Reading · draft-before-merge + fullscreen weekly ND"
        className="floating-draft-before-full-merge-fullscreen-weekly-nd-mo-panel"
      >
        <p className="text-sm opacity-80" data-testid="fdbfm-fs-weekly-blurb">
          Provisional combined draft over fullscreen float + Antiek-bench weekly
          learn + ND multi-select pack. Pure — never writes, merges, or
          production-routes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="fdbfm-fs-weekly-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="fdbfm-fs-weekly-compose"
          >
            Compose pack
          </LemonButton>
          {error && (
            <p
              className="text-sm text-danger"
              data-testid="fdbfm-fs-weekly-error"
            >
              {error}
            </p>
          )}
          {result && (
            <pre
              className="text-xs mt-2 p-2 bg-bg-light rounded overflow-auto max-h-64"
              data-testid="fdbfm-fs-weekly-result"
            >
              {formatFloatingDraftBeforeFullMergeFullscreenWeeklyNdMoSummary(
                result,
              )}
              {"\n"}
              pack_ready={String(result.pack_ready)}
              {" · "}
              draft_written={String(result.draft_written)}
              {" · "}
              merge_executed={String(result.merge_executed)}
              {" · "}
              verdict={result.production_router_verdict}
            </pre>
          )}
        </div>
      </LemonCard>
    </div>
  );
}
