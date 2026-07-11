/**
 * MidnightOilTimeGoalsPriceEntryPanel — MO operator entry form.
 *
 * Free-file. live_execution_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilTimeGoalsPriceEntry,
  formatMidnightOilTimeGoalsPriceEntrySummary,
  type MidnightOilTimeGoalsPriceEntryCompose,
} from "../../api/midnightOilTimeGoalsPriceEntryCompose";

export interface MidnightOilTimeGoalsPriceEntryPanelProps {
  composeFn?: typeof composeMidnightOilTimeGoalsPriceEntry;
}

export default function MidnightOilTimeGoalsPriceEntryPanel({
  composeFn = composeMidnightOilTimeGoalsPriceEntry,
}: MidnightOilTimeGoalsPriceEntryPanelProps) {
  const [operatorId, setOperatorId] = useState("op-1");
  const [minutes, setMinutes] = useState("120");
  const [goalTitle, setGoalTitle] = useState("Survey arxiv");
  const [rate, setRate] = useState("15");
  const [approved, setApproved] = useState("40");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilTimeGoalsPriceEntryCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          operator_id: operatorId.trim(),
          work_minutes: Number(minutes),
          goals: [
            { goal_id: "g1", title: goalTitle.trim() || "goal" },
            { goal_id: "g2", title: "Draft notes" },
          ],
          usd_per_hour: rate.trim() === "" ? null : Number(rate),
          approved_ceiling_usd:
            approved.trim() === "" ? null : Number(approved),
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="midnight-oil-time-goals-price-entry-panel">
      <LemonCard
        title="Midnight Oil · time + goals + price entry"
        className="midnight-oil-time-goals-price-entry-panel"
      >
        <p className="text-sm opacity-80" data-testid="motgpe-blurb">
          Set work window and goals; see recommended price ceiling to approve.
          Pure — live_execution_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator id</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="motgpe-op"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="motgpe-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goal title</span>
            <LemonInput
              value={goalTitle}
              onChange={(e) => setGoalTitle(e.target.value)}
              data-testid="motgpe-goal"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>USD per hour (for rec)</span>
            <LemonInput
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              data-testid="motgpe-rate"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved ceiling USD</span>
            <LemonInput
              value={approved}
              onChange={(e) => setApproved(e.target.value)}
              data-testid="motgpe-approved"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="motgpe-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="motgpe-compose"
          >
            Compose MO entry
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="motgpe-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="motgpe-result"
            >
              <div data-testid="motgpe-ready">
                entry_ready={String(result.entry_ready)}
              </div>
              <div data-testid="motgpe-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="motgpe-rec">
                recommended=
                {result.recommend.recommended_ceiling_usd === null
                  ? "null"
                  : String(result.recommend.recommended_ceiling_usd)}
              </div>
              <div data-testid="motgpe-summary">
                {formatMidnightOilTimeGoalsPriceEntrySummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
