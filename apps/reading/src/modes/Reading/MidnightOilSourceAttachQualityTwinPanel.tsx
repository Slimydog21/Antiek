/**
 * MidnightOilSourceAttachQualityTwinPanel — MO + sources → twin.
 *
 * Free-file. live_execution / twin_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilSourceAttachQualityTwin,
  formatMidnightOilSourceAttachQualityTwinSummary,
  type MidnightOilSourceAttachQualityTwinCompose,
} from "../../api/midnightOilSourceAttachQualityTwinCompose";

export interface MidnightOilSourceAttachQualityTwinPanelProps {
  composeFn?: typeof composeMidnightOilSourceAttachQualityTwin;
}

export default function MidnightOilSourceAttachQualityTwinPanel({
  composeFn = composeMidnightOilSourceAttachQualityTwin,
}: MidnightOilSourceAttachQualityTwinPanelProps) {
  const [minutes, setMinutes] = useState("120");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilSourceAttachQualityTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          operator_id: "op-demo",
          work_minutes: Math.max(1, parseInt(minutes, 10) || 120),
          goals: [
            { goal_id: "g1", title: "Survey arxiv scaling laws" },
            { goal_id: "g2", title: "Synthesize substack claims" },
          ],
          usd_per_hour: 15,
          approved_ceiling_usd: 40,
          operator_ack: ack,
          unattended_ack: ack,
          spend_consent: ack,
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          requested_families: ["arxiv", "substack"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo arXiv paper",
              html_fragment: "<article>HTML</article>",
            },
            {
              source_id: "sub-demo",
              family: "substack",
              title: "Demo essay",
              html_fragment: "<article>essay</article>",
            },
          ],
          quality_overall: 0.85,
          quality_floor: 0.7,
          would_exceed: false,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="midnight-oil-source-attach-quality-twin-panel">
      <LemonCard
        title="Midnight Oil · sources → twin feed"
        className="midnight-oil-source-attach-quality-twin-panel"
      >
        <p className="text-sm opacity-80" data-testid="mosaqt-blurb">
          Unattended MO with arxiv/substack, then feed goals+sources into
          recursive twin. Pure — never launches or writes twin.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="mosaqt-minutes"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mosaqt-ack"
            />
            <span>acks</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="mosaqt-compose"
          >
            Compose MO + twin
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="mosaqt-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="mosaqt-result">
            <p data-testid="mosaqt-summary">
              {formatMidnightOilSourceAttachQualityTwinSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>mo_source_ready={String(result.mo_source.pack_ready)}</li>
              <li>twin_feed_ready={String(result.twin_feed.feed_ready)}</li>
              <li>twin_written={String(result.twin_written)}</li>
              <li>
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
