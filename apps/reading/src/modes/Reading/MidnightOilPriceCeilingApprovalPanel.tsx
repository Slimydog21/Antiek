/**
 * MidnightOilPriceCeilingApprovalPanel — recommend → approve ceiling.
 *
 * Free-file. live_execution/charge always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilPriceCeilingApproval,
  formatMidnightOilPriceCeilingApprovalSummary,
  type MidnightOilPriceCeilingApprovalCompose,
  type MoPriceCeilingStage,
} from "../../api/midnightOilPriceCeilingApprovalCompose";

export interface MidnightOilPriceCeilingApprovalPanelProps {
  composeFn?: typeof composeMidnightOilPriceCeilingApproval;
}

export default function MidnightOilPriceCeilingApprovalPanel({
  composeFn = composeMidnightOilPriceCeilingApproval,
}: MidnightOilPriceCeilingApprovalPanelProps) {
  const [minutes, setMinutes] = useState("120");
  const [rate, setRate] = useState("30");
  const [stage, setStage] = useState<MoPriceCeilingStage>("recommend_only");
  const [ack, setAck] = useState(true);
  const [priceAck, setPriceAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilPriceCeilingApprovalCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const work_minutes = Number(minutes) || 60;
      const usd_per_hour = Number(rate) || 30;
      const recFirst = composeFn({
        operator_id: "op-demo",
        work_minutes,
        goals: [
          { goal_id: "g1", title: "Deep research goal A" },
          { goal_id: "g2", title: "Deep research goal B" },
        ],
        usd_per_hour,
        price_ceiling_ack: false,
        operator_ack: false,
        stage: "recommend_only",
      });
      const recommended =
        recFirst.recommend.recommended_ceiling_usd ?? usd_per_hour;
      setResult(
        composeFn({
          operator_id: "op-demo",
          work_minutes,
          goals: [
            { goal_id: "g1", title: "Deep research goal A" },
            { goal_id: "g2", title: "Deep research goal B" },
          ],
          usd_per_hour,
          approved_ceiling_usd:
            stage === "recommend_only" ? null : recommended,
          price_ceiling_ack: priceAck,
          operator_ack: ack,
          unattended_ack: stage === "unattended_pack" ? true : undefined,
          spend_consent: stage === "unattended_pack" ? true : undefined,
          stage,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="midnight-oil-price-ceiling-approval-panel">
      <LemonCard
        title="Midnight Oil · recommend → approve price ceiling"
        className="midnight-oil-price-ceiling-approval-panel"
      >
        <p className="text-sm opacity-80" data-testid="mopca-blurb">
          System recommends a price ceiling from time + goals; approve before
          unattended pack. Pure — never charges or launches workers.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="mopca-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>USD per hour</span>
            <LemonInput
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              data-testid="mopca-rate"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Stage</span>
            <select
              value={stage}
              onChange={(e) =>
                setStage(e.target.value as MoPriceCeilingStage)
              }
              data-testid="mopca-stage"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="recommend_only">recommend_only</option>
              <option value="approve_ceiling">approve_ceiling</option>
              <option value="unattended_pack">unattended_pack</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={priceAck}
              onChange={(e) => setPriceAck(e.target.checked)}
              data-testid="mopca-price-ack"
            />
            <span>price_ceiling_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mopca-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="mopca-compose"
          >
            Compose MO ceiling flow
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="mopca-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="mopca-result">
            <p data-testid="mopca-summary">
              {formatMidnightOilPriceCeilingApprovalSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                recommended=
                {result.recommend.recommended_ceiling_usd ?? "null"}
              </li>
              <li>ceiling_approved={String(result.ceiling_approved)}</li>
              <li>
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </li>
              <li>charge_executed={String(result.charge_executed)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
