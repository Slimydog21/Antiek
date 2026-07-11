/**
 * MidnightOilUnattendedRecapPanel — post-run recap for unattended MO.
 *
 * Free-file. live_execution_authorized and store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilUnattendedRecap,
  formatMidnightOilUnattendedRecapSummary,
  type MidnightOilUnattendedRecapCompose,
} from "../../api/midnightOilUnattendedRecapCompose";

export interface MidnightOilUnattendedRecapPanelProps {
  composeFn?: typeof composeMidnightOilUnattendedRecap;
}

export default function MidnightOilUnattendedRecapPanel({
  composeFn = composeMidnightOilUnattendedRecap,
}: MidnightOilUnattendedRecapPanelProps) {
  const [runId, setRunId] = useState("mo-1");
  const [operatorId, setOperatorId] = useState("op-1");
  const [planned, setPlanned] = useState("120");
  const [actual, setActual] = useState("110");
  const [ceiling, setCeiling] = useState("25");
  const [spend, setSpend] = useState("18.5");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilUnattendedRecapCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          run_id: runId.trim(),
          operator_id: operatorId.trim(),
          work_minutes_planned: Number(planned),
          work_minutes_actual: actual.trim() === "" ? null : Number(actual),
          price_ceiling_usd: ceiling.trim() === "" ? null : Number(ceiling),
          spend_usd: spend.trim() === "" ? null : Number(spend),
          operator_ack: ack,
          artifact_ids: ["art-1"],
          goals: [
            { goal_id: "g1", title: "Survey arxiv", status: "done" },
            { goal_id: "g2", title: "Draft notes", status: "blocked" },
            { goal_id: "g3", title: "Follow-ups", status: "pending" },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="midnight-oil-unattended-recap-panel">
      <LemonCard
        title="Midnight Oil · unattended recap"
        className="midnight-oil-unattended-recap-panel"
      >
        <p className="text-sm opacity-80" data-testid="mour-blurb">
          After an unattended MO window: goals progress, spend vs ceiling,
          artifacts. Pure — live_execution_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Run id</span>
            <LemonInput
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              data-testid="mour-run"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Operator id</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="mour-op"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm flex flex-col gap-1">
              <span>Planned minutes</span>
              <LemonInput
                value={planned}
                onChange={(e) => setPlanned(e.target.value)}
                data-testid="mour-planned"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Actual minutes</span>
              <LemonInput
                value={actual}
                onChange={(e) => setActual(e.target.value)}
                data-testid="mour-actual"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Ceiling USD</span>
              <LemonInput
                value={ceiling}
                onChange={(e) => setCeiling(e.target.value)}
                data-testid="mour-ceiling"
              />
            </label>
            <label className="text-sm flex flex-col gap-1">
              <span>Spend USD</span>
              <LemonInput
                value={spend}
                onChange={(e) => setSpend(e.target.value)}
                data-testid="mour-spend"
              />
            </label>
          </div>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mour-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mour-compose"
          >
            Compose recap
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="mour-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="mour-result"
            >
              <div data-testid="mour-ready">
                recap_ready={String(result.recap_ready)}
              </div>
              <div data-testid="mour-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="mour-ceiling-flag">
                within_ceiling=
                {result.within_ceiling === null
                  ? "null"
                  : String(result.within_ceiling)}
              </div>
              <div data-testid="mour-summary">
                {formatMidnightOilUnattendedRecapSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
