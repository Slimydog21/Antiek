/**
 * MidnightOilSwarmReadinessPanel - unattended handoff readiness for MO swarm.
 *
 * Free-file. live_execution_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  evaluateMidnightOilSwarmReadiness,
  formatSwarmReadinessSummary,
  type MidnightOilSwarmReadinessDecision,
} from "../../api/midnightOilSwarmReadiness";

export interface MidnightOilSwarmReadinessPanelProps {
  evaluateFn?: typeof evaluateMidnightOilSwarmReadiness;
  initialOperatorId?: string;
}

export default function MidnightOilSwarmReadinessPanel({
  evaluateFn = evaluateMidnightOilSwarmReadiness,
  initialOperatorId = "",
}: MidnightOilSwarmReadinessPanelProps) {
  const [operatorId, setOperatorId] = useState(initialOperatorId);
  const [minutesRaw, setMinutesRaw] = useState("60");
  const [goalsRaw, setGoalsRaw] = useState("2");
  const [ceilingRaw, setCeilingRaw] = useState("5");
  const [recommendedRaw, setRecommendedRaw] = useState("4");
  const [briefReady, setBriefReady] = useState(true);
  const [unattendedAck, setUnattendedAck] = useState(false);
  const [spendConsent, setSpendConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilSwarmReadinessDecision | null>(null);

  function parseOptionalMoney(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) {
      throw new Error("money field must be finite or blank");
    }
    return n;
  }

  function onEval() {
    setError(null);
    setResult(null);
    try {
      setResult(
        evaluateFn({
          operator_id: operatorId.trim(),
          work_minutes: Number(minutesRaw),
          goal_count: Number(goalsRaw),
          price_ceiling_usd: parseOptionalMoney(ceilingRaw),
          recommended_ceiling_usd: parseOptionalMoney(recommendedRaw),
          brief_dispatch_ready: briefReady,
          unattended_ack: unattendedAck,
          spend_consent: spendConsent,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-swarm-readiness-panel">
      <LemonCard
        title="Midnight Oil swarm readiness"
        className="mo-swarm-readiness-panel"
      >
        <p className="text-sm opacity-80" data-testid="mosr-blurb">
          Check whether an unattended swarm handoff is ready: goals, time,
          price ceiling, spend consent, and brief approval.
          live_execution_authorized always stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator id</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="mosr-operator"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutesRaw}
              onChange={(e) => setMinutesRaw(e.target.value)}
              data-testid="mosr-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goal count</span>
            <LemonInput
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="mosr-goals"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Price ceiling USD (blank = unknown)</span>
            <LemonInput
              value={ceilingRaw}
              onChange={(e) => setCeilingRaw(e.target.value)}
              data-testid="mosr-ceiling"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Recommended ceiling USD</span>
            <LemonInput
              value={recommendedRaw}
              onChange={(e) => setRecommendedRaw(e.target.value)}
              data-testid="mosr-recommended"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={briefReady}
              onChange={(e) => setBriefReady(e.target.checked)}
              data-testid="mosr-brief"
            />
            brief_dispatch_ready
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={spendConsent}
              onChange={(e) => setSpendConsent(e.target.checked)}
              data-testid="mosr-consent"
            />
            spend_consent
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={unattendedAck}
              onChange={(e) => setUnattendedAck(e.target.checked)}
              data-testid="mosr-ack"
            />
            unattended_ack
          </label>
          <LemonButton
            variant="primary"
            onClick={onEval}
            data-testid="mosr-run"
          >
            Evaluate swarm readiness
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="mosr-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="mosr-result" className="text-sm flex flex-col gap-1">
              <div data-testid="mosr-summary">
                {formatSwarmReadinessSummary(result)}
              </div>
              <div data-testid="mosr-unattended">
                unattended_ready={String(result.unattended_ready)}
              </div>
              <div data-testid="mosr-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
