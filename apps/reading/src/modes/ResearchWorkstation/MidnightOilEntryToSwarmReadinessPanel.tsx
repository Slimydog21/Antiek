/**
 * MidnightOilEntryToSwarmReadinessPanel — entry + unattended readiness pack.
 *
 * Free-file. live_execution_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilEntryToSwarmReadiness,
  formatMidnightOilEntryToSwarmReadinessSummary,
  type MidnightOilEntryToSwarmReadinessCompose,
} from "../../api/midnightOilEntryToSwarmReadinessCompose";

export interface MidnightOilEntryToSwarmReadinessPanelProps {
  composeFn?: typeof composeMidnightOilEntryToSwarmReadiness;
}

export default function MidnightOilEntryToSwarmReadinessPanel({
  composeFn = composeMidnightOilEntryToSwarmReadiness,
}: MidnightOilEntryToSwarmReadinessPanelProps) {
  const [operatorId, setOperatorId] = useState("op-1");
  const [minutes, setMinutes] = useState("120");
  const [ceiling, setCeiling] = useState("40");
  const [ack, setAck] = useState(true);
  const [unattended, setUnattended] = useState(true);
  const [brief, setBrief] = useState(true);
  const [consent, setConsent] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilEntryToSwarmReadinessCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const work_minutes = Number(minutes);
      const approved_ceiling_usd = ceiling.trim()
        ? Number(ceiling)
        : null;
      setResult(
        composeFn({
          operator_id: operatorId.trim(),
          work_minutes,
          goals: [
            { goal_id: "g1", title: "Survey arxiv" },
            { goal_id: "g2", title: "Draft notes" },
          ],
          usd_per_hour: 15,
          approved_ceiling_usd,
          operator_ack: ack,
          brief_dispatch_ready: brief,
          unattended_ack: unattended,
          spend_consent: consent,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-entry-to-swarm-readiness-panel">
      <LemonCard
        title="Midnight Oil · entry → swarm readiness"
        className="mo-entry-to-swarm-readiness-panel"
      >
        <p className="text-sm opacity-80" data-testid="moesr-blurb">
          Time + goals + price ceiling entry, then unattended swarm readiness.
          Pure — live_execution_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="moesr-op"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="moesr-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved ceiling USD</span>
            <LemonInput
              value={ceiling}
              onChange={(e) => setCeiling(e.target.value)}
              data-testid="moesr-ceiling"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="moesr-ack"
            />
            <span>operator_ack (entry)</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={brief}
              onChange={(e) => setBrief(e.target.checked)}
              data-testid="moesr-brief"
            />
            <span>brief_dispatch_ready</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={unattended}
              onChange={(e) => setUnattended(e.target.checked)}
              data-testid="moesr-unattended"
            />
            <span>unattended_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              data-testid="moesr-consent"
            />
            <span>spend_consent</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="moesr-compose"
          >
            Compose MO entry → readiness
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="moesr-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="moesr-result"
            >
              <div data-testid="moesr-ready">
                package_ready={String(result.package_ready)}
              </div>
              <div data-testid="moesr-entry">
                entry_ready={String(result.entry.entry_ready)}
              </div>
              <div data-testid="moesr-unatt">
                unattended_ready={String(result.readiness.unattended_ready)}
              </div>
              <div data-testid="moesr-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="moesr-summary">
                {formatMidnightOilEntryToSwarmReadinessSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
