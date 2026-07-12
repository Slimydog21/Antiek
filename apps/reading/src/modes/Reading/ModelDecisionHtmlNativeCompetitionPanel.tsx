/**
 * ModelDecisionHtmlNativeCompetitionPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeModelDecisionHtmlNativeCompetition,
  formatModelDecisionHtmlNativeCompetitionSummary,
  type ModelDecisionHtmlNativeCompetitionCompose,
} from "../../api/modelDecisionHtmlNativeCompetitionCompose";

export default function ModelDecisionHtmlNativeCompetitionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ModelDecisionHtmlNativeCompetitionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeModelDecisionHtmlNativeCompetition({
          decision: {
            selected_model_id: "gpt-5.5",
            models: [
              {
                model_id: "gpt-5.5",
                tier: "frontier",
                projected_cost_usd_high: 2,
                projected_cost_usd_low: 1,
              },
              {
                model_id: "grok-4.5",
                tier: "fast",
                projected_cost_usd_high: 0.5,
                projected_cost_usd_low: 0.2,
              },
            ],
            daily_cap_usd: 50,
            spent_usd: 10,
          },
          competition_view: {
            session_id: "sess-demo",
            asset_id: "asset-demo",
            html_projection_sha: "sha-html-demo",
            view_requested: true,
            twin_bound: true,
            twin_substrate_ready: true,
            claimed_format: "html",
            competition: {
              draft_id: "draft-demo",
              parent_asset_id: "asset-demo",
              competitor_decisions: [
                {
                  competitor: "Perplexity",
                  area: "citation_grounding",
                  decision_summary: "Inline citations with source cards",
                  antiek_status: "parity",
                },
                {
                  competitor: "OpenAI DR",
                  area: "multi_agent_orchestration",
                  decision_summary: "Planner + browser agents",
                  antiek_status: "behind",
                  residual: "strengthen collective floating cohesive pack",
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
              quality_floor: 0.5,
              would_exceed: false,
              search_query: "scaling orchestration citations",
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
    <div data-testid="model-decision-html-native-competition-panel">
      <LemonCard title="Research · model decision + HTML-native competition">
        <p className="text-sm opacity-80">
          Model decision tree with usage bar/projection over competition quality
          → write → twin search, HTML-native only. Pure — no live router.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="mdhnc-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="mdhnc-compose"
        >
          Compose model decision + competition pack
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="mdhnc-result">
            <p>{formatModelDecisionHtmlNativeCompetitionSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>would_exceed={String(result.decision.would_exceed)}</li>
              <li>
                live_router_authorized={String(result.live_router_authorized)}
              </li>
              <li>pdf_view_authorized={String(result.pdf_view_authorized)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
