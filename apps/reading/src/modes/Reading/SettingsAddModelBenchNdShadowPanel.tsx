/**
 * SettingsAddModelBenchNdShadowPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsAddModelBenchNdShadow,
  formatSettingsAddModelBenchNdShadowSummary,
  type SettingsAddModelBenchNdShadowCompose,
} from "../../api/settingsAddModelBenchNdShadowCompose";

export default function SettingsAddModelBenchNdShadowPanel() {
  const [pending, setPending] = useState("mimo-v2");
  const [killSwitch, setKillSwitch] = useState(true);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsAddModelBenchNdShadowCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const pending_ids = pending
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeSettingsAddModelBenchNdShadow({
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
          nd_recommended_model_id: "gpt-5.5",
          kill_switch_on: killSwitch,
          nd_confidence: 0.6,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-add-model-bench-nd-shadow-panel">
      <LemonCard title="Settings · add model + bench + ND shadow (REJECT)">
        <p className="text-sm opacity-80">
          BYOK add-model, Antiek-bench recommend, usage bar, and NotDiamond
          shadow only. Production router verdict always REJECT.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <LemonInput
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            data-testid="sambnd-pending"
          />
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={killSwitch}
              onChange={(e) => setKillSwitch(e.target.checked)}
              data-testid="sambnd-kill"
            />
            ND kill_switch_on
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="sambnd-ack"
            />
            operator_ack
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="sambnd-compose"
          >
            Compose settings quality + ND shadow
          </LemonButton>
        </div>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="sambnd-result">
            <p>{formatSettingsAddModelBenchNdShadowSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                production_router_verdict={result.production_router_verdict}
              </li>
              <li>bench_vs_nd={result.bench_vs_nd}</li>
              <li>live_router={String(result.live_router_authorized)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
