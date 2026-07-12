/**
 * SettingsAddModelBenchDecisionPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsAddModelBenchDecision,
  formatSettingsAddModelBenchDecisionSummary,
  type SettingsAddModelBenchDecisionCompose,
} from "../../api/settingsAddModelBenchDecisionCompose";

export default function SettingsAddModelBenchDecisionPanel() {
  const [pending, setPending] = useState("mimo-v2");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsAddModelBenchDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const pending_ids = pending
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeSettingsAddModelBenchDecision({
          models: [
            { model_id: "gpt-5.5", provider: "openai" },
            { model_id: "grok-4.5", provider: "xai" },
          ],
          pending_add_model_ids: pending_ids.length
            ? pending_ids
            : ["mimo-v2"],
          action: "preview",
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
          decision_models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
            { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
          ],
          daily_cap_usd: 20,
          spent_usd: 5,
          projected_cost_usd_high: 0.5,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-add-model-bench-decision-panel">
      <LemonCard title="Settings · add model + Antiek-bench decision">
        <p className="text-sm opacity-80">
          BYOK inventory propose with task model recommendation, usage bar, and
          prompt projection. Pure — no secrets, no auto-route.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Pending model ids (comma-separated)</span>
            <LemonInput
              value={pending}
              onChange={(e) => setPending(e.target.value)}
              data-testid="sambd-pending"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="sambd-ack"
            />
            operator_ack
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="sambd-compose"
          >
            Compose settings quality surface
          </LemonButton>
        </div>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="sambd-result">
            <p>{formatSettingsAddModelBenchDecisionSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                recommend=
                {result.bench_rec.recommendation?.recommended_model_id ??
                  "none"}
              </li>
              <li>
                would_exceed=
                {String(result.bench_rec.decision_tree.would_exceed)}
              </li>
              <li>inventory_mutated={String(result.inventory_mutated)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
