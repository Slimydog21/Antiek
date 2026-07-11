/**
 * NotDiamondBenchDecisionShadowPanel — bench + ND shadow (REJECT router).
 *
 * Free-file. live_router always false; production_router_verdict=REJECT.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeNotDiamondBenchDecisionShadow,
  formatNotDiamondBenchDecisionShadowSummary,
  type NotDiamondBenchDecisionShadowCompose,
} from "../../api/notDiamondBenchDecisionShadowCompose";

export interface NotDiamondBenchDecisionShadowPanelProps {
  composeFn?: typeof composeNotDiamondBenchDecisionShadow;
}

export default function NotDiamondBenchDecisionShadowPanel({
  composeFn = composeNotDiamondBenchDecisionShadow,
}: NotDiamondBenchDecisionShadowPanelProps) {
  const [kill, setKill] = useState(false);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NotDiamondBenchDecisionShadowCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
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
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.5 },
            { model_id: "mimo-v2", projected_cost_usd_high: 0.1 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.3 },
          ],
          daily_cap_usd: 25,
          spent_usd: 3,
          projected_cost_usd_high: 0.5,
          nd_recommended_model_id: "gpt-5.5",
          kill_switch_on: kill,
          nd_confidence: 0.75,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="notdiamond-bench-decision-shadow-panel">
      <LemonCard
        title="Settings · Antiek-bench + NotDiamond shadow (REJECT router)"
        className="notdiamond-bench-decision-shadow-panel"
      >
        <p className="text-sm opacity-80" data-testid="ndbds-blurb">
          Weekly bench recommendation beside NotDiamond shadow. Production
          router stays REJECT — operator selects the model.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={kill}
              onChange={(e) => setKill(e.target.checked)}
              data-testid="ndbds-kill"
            />
            <span>ND kill_switch_on</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="ndbds-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="ndbds-compose"
          >
            Compose bench + ND shadow
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="ndbds-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="ndbds-result">
            <p data-testid="ndbds-summary">
              {formatNotDiamondBenchDecisionShadowSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>bench_vs_nd={result.bench_vs_nd}</li>
              <li>
                production_router_verdict=
                {result.production_router_verdict}
              </li>
              <li>
                live_router_authorized=
                {String(result.live_router_authorized)}
              </li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
