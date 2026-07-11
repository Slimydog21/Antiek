/**
 * MidnightOilRecapWriteModeTwinCollectivePanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMidnightOilRecapWriteModeTwinCollective,
  formatMidnightOilRecapWriteModeTwinCollectiveSummary,
  type MidnightOilRecapWriteModeTwinCollectiveCompose,
} from "../../api/midnightOilRecapWriteModeTwinCollectiveCompose";

export default function MidnightOilRecapWriteModeTwinCollectivePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilRecapWriteModeTwinCollectiveCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeMidnightOilRecapWriteModeTwinCollective({
          run_id: "run-demo",
          operator_id: "op-demo",
          work_minutes_planned: 120,
          work_minutes_actual: 110,
          goals: [
            {
              goal_id: "g1",
              title: "Survey arxiv",
              status: "done",
              notes: "Found papers",
            },
            {
              goal_id: "g2",
              title: "Synthesize",
              status: "done",
              notes: "Draft ready",
            },
          ],
          price_ceiling_usd: 40,
          spend_usd: 25,
          artifact_ids: ["art-demo"],
          operator_ack: ack,
          session_id: "sess-demo",
          draft_id: "draft-demo",
          parent_asset_id: "asset-demo",
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-recap-write-mode-twin-collective-panel">
      <LemonCard title="Midnight Oil · recap → write twin/analysis">
        <p className="text-sm opacity-80">
          Unattended MO recap folds into write draft + collective analysis.
          Pure.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="morw-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="morw-compose"
        >
          Compose recap → write
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="morw-result">
            <p>
              {formatMidnightOilRecapWriteModeTwinCollectiveSummary(result)}
            </p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>draft_written={String(result.draft_written)}</li>
              <li>analysis_written={String(result.analysis_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
