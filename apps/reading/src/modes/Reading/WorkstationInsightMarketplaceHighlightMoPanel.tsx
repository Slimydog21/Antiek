/**
 * WorkstationInsightMarketplaceHighlightMoPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWorkstationInsightMarketplaceHighlightMo,
  formatWorkstationInsightMarketplaceHighlightMoSummary,
  type WorkstationInsightMarketplaceHighlightMoCompose,
} from "../../api/workstationInsightMarketplaceHighlightMoCompose";

export default function WorkstationInsightMarketplaceHighlightMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WorkstationInsightMarketplaceHighlightMoCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeWorkstationInsightMarketplaceHighlightMo({
          records: {
            session_id: "sess-demo",
            parent_asset_id: "book-demo",
            records: [
              {
                record_id: "r1",
                kind: "insight",
                body: "Power-law scaling holds in compute-optimal regimes",
              },
              {
                record_id: "r2",
                kind: "question",
                body: "What residual gaps remain vs OpenAI DR?",
              },
            ],
            operator_ack: ack,
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
                    { goal_id: "g1", title: "Survey arxiv competition gaps" },
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
                          decision_summary: "Planner + browser agents",
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
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="workstation-insight-marketplace-highlight-mo-panel">
      <LemonCard title="Research · workstation records → marketplace MO pack">
        <p className="text-sm opacity-80">
          Session insights/questions inform marketplace HTML book → highlight
          float → recursive twin MO competition. Pure — no persist, no live.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="wimhm-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="wimhm-compose"
        >
          Compose records → marketplace MO pack
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="wimhm-result">
            <p>
              {formatWorkstationInsightMarketplaceHighlightMoSummary(result)}
            </p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>record_count={result.records.record_count}</li>
              <li>record_persisted={String(result.record_persisted)}</li>
              <li>prompts_injected={String(result.prompts_injected)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
