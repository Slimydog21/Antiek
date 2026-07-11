/**
 * AntiekBenchTaskModelRecommendationPanel — bench learn → model rec → tree.
 *
 * Free-file. live_router/secrets/suite rewrite always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeAntiekBenchTaskModelRecommendation,
  formatAntiekBenchTaskModelRecommendationSummary,
  type AntiekBenchTaskModelRecommendationCompose,
} from "../../api/antiekBenchTaskModelRecommendationCompose";

export interface AntiekBenchTaskModelRecommendationPanelProps {
  composeFn?: typeof composeAntiekBenchTaskModelRecommendation;
}

export default function AntiekBenchTaskModelRecommendationPanel({
  composeFn = composeAntiekBenchTaskModelRecommendation,
}: AntiekBenchTaskModelRecommendationPanelProps) {
  const [task, setTask] = useState("deep_research");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchTaskModelRecommendationCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          week_id: "2026-W28",
          focus_task: task.trim() || "deep_research",
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
              score: 0.88,
            },
            {
              event_id: "e3",
              task: "deep_research",
              model_id: "mimo-v2",
              outcome: "failed",
              score: 0.3,
            },
            {
              event_id: "e4",
              task: "deep_research",
              model_id: "mimo-v2",
              outcome: "failed",
              score: 0.25,
            },
          ],
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
            { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
          ],
          daily_cap_usd: 25,
          spent_usd: 4,
          projected_cost_usd_high: 0.5,
          operator_ack: ack,
          existing_tasks: ["deep_research", "twin_notes"],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="antiek-bench-task-model-recommendation-panel">
      <LemonCard
        title="Settings · Antiek-bench → model recommendation"
        className="antiek-bench-task-model-recommendation-panel"
      >
        <p className="text-sm opacity-80" data-testid="abtmr-blurb">
          Weekly usage-learn proposes the best model for a task family and
          surfaces it in the decision tree with budget projection. Pure
          advisory — never auto-routes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Focus task</span>
            <LemonInput
              value={task}
              onChange={(e) => setTask(e.target.value)}
              data-testid="abtmr-task"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="abtmr-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="abtmr-compose"
          >
            Compose bench → model rec
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="abtmr-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="abtmr-result">
            <p data-testid="abtmr-summary">
              {formatAntiekBenchTaskModelRecommendationSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                rec=
                {result.recommendation?.recommended_model_id ?? "none"}
              </li>
              <li>
                selected=
                {result.decision_tree.driver.decision.selected_model_id}
              </li>
              <li>
                live_router_authorized=
                {String(result.live_router_authorized)}
              </li>
              <li>suite_rewritten={String(result.suite_rewritten)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
