/**
 * FloatingFullscreenAntiekBenchWeeklyNdMoPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingFullscreenAntiekBenchWeeklyNdMo,
  formatFloatingFullscreenAntiekBenchWeeklyNdMoSummary,
  type FloatingFullscreenAntiekBenchWeeklyNdMoCompose,
} from "../../api/floatingFullscreenAntiekBenchWeeklyNdMoCompose";

export default function FloatingFullscreenAntiekBenchWeeklyNdMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingFullscreenAntiekBenchWeeklyNdMoCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFloatingFullscreenAntiekBenchWeeklyNdMo({
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
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-fullscreen-antiek-bench-weekly-nd-mo-panel">
      <LemonCard title="Research · fullscreen float + weekly ND multi-select">
        <p className="text-sm opacity-80">
          Open floating deep research fullscreen while Antiek-bench weekly
          learn + ND multi-select pack stays ready. Pure — no live dispatch.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="ffabwn-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="ffabwn-compose"
        >
          Compose fullscreen + weekly ND pack
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="ffabwn-result">
            <p>
              {formatFloatingFullscreenAntiekBenchWeeklyNdMoSummary(result)}
            </p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                fullscreen_ready={String(result.fullscreen.fullscreen_ready)}
              </li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
              <li>
                production_router_verdict={result.production_router_verdict}
              </li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
