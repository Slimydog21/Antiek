/**
 * RecursiveTwinMoCompetitionPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinMoCompetition,
  formatRecursiveTwinMoCompetitionSummary,
  type RecursiveTwinMoCompetitionCompose,
} from "../../api/recursiveTwinMoCompetitionCompose";

export default function RecursiveTwinMoCompetitionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinMoCompetitionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeRecursiveTwinMoCompetition({
          parent_asset_id: "asset-demo",
          mo: {
            operator_id: "op-demo",
            work_minutes: 120,
            goals: [
              { goal_id: "g1", title: "Survey arxiv competition gaps" },
              { goal_id: "g2", title: "Draft twin notes" },
            ],
            usd_per_hour: 15,
            approved_ceiling_usd: 40,
            operator_ack: ack,
            unattended_ack: true,
            spend_consent: true,
          },
          research: {
            decision: {
              selected_model_id: "gpt-5.5",
              models: [
                {
                  model_id: "gpt-5.5",
                  tier: "frontier",
                  projected_cost_usd_high: 2,
                  projected_cost_usd_low: 1,
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
          },
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-mo-competition-panel">
      <LemonCard title="Research · recursive twin + MO competition pack">
        <p className="text-sm opacity-80">
          Twin note-taker scaffold over midnight oil + model decision +
          HTML-native competition research. Pure — no twin write, no live
          workers.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="rtmoc-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="rtmoc-compose"
        >
          Compose twin + MO competition
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="rtmoc-result">
            <p>{formatRecursiveTwinMoCompetitionSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>twin_written={String(result.twin_written)}</li>
              <li>
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
