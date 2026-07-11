/**
 * CompetitionQualityInterrogationLoopPanel — world-class DR + chase loop.
 *
 * Free-file. live_dispatch/remote_fetch/record always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeCompetitionQualityInterrogationLoop,
  formatCompetitionQualityInterrogationLoopSummary,
  type CompetitionQualityInterrogationLoopCompose,
} from "../../api/competitionQualityInterrogationLoopCompose";

export interface CompetitionQualityInterrogationLoopPanelProps {
  composeFn?: typeof composeCompetitionQualityInterrogationLoop;
}

export default function CompetitionQualityInterrogationLoopPanel({
  composeFn = composeCompetitionQualityInterrogationLoop,
}: CompetitionQualityInterrogationLoopPanelProps) {
  const [prompt, setPrompt] = useState(
    "Chase competitor gaps with arxiv/substack rigor",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionQualityInterrogationLoopCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
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
              title: "Scaling Laws paper",
              external_id: "arxiv:2001.08361",
            },
            {
              citation_id: "c2",
              family: "substack",
              title: "Research essay",
            },
          ],
          quality_overall: 0.86,
          quality_floor: 0.7,
          would_exceed: false,
          questions: [
            {
              question_id: "q1",
              body: "How do competitors structure multi-hop citations?",
              priority: 2,
            },
            {
              question_id: "q2",
              body: "Where is Antiek ahead on HTML-native research?",
              priority: 1,
            },
          ],
          chase_mode: "swarm_fanout",
          user_prompt: prompt.trim() || "Chase gaps",
          selected_model_id: "gpt-5.5",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          daily_cap_usd: 30,
          spent_usd: 3,
          projected_cost_usd_high: 0.4,
          source_families: ["arxiv", "substack"],
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-quality-interrogation-loop-panel">
      <LemonCard
        title="Research · competition quality + interrogation"
        className="competition-quality-interrogation-loop-panel"
      >
        <p className="text-sm opacity-80" data-testid="cqil-blurb">
          Hold the world-class deep research bar (competition + citations +
          quality/budget) while chasing questions in the workstation. Pure —
          never dispatches or scrapes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="cqil-prompt"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="cqil-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="cqil-compose"
          >
            Compose quality + interrogation
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="cqil-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="cqil-result">
            <p data-testid="cqil-summary">
              {formatCompetitionQualityInterrogationLoopSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>session_ready={String(result.session_ready)}</li>
              <li>
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
              <li>record_persisted={String(result.record_persisted)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
