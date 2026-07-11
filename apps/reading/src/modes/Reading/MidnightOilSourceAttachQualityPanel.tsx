/**
 * MidnightOilSourceAttachQualityPanel — unattended MO + arxiv/substack.
 *
 * Free-file. live_execution / remote_fetched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilSourceAttachQuality,
  formatMidnightOilSourceAttachQualitySummary,
  type MidnightOilSourceAttachQualityCompose,
} from "../../api/midnightOilSourceAttachQualityCompose";

export interface MidnightOilSourceAttachQualityPanelProps {
  composeFn?: typeof composeMidnightOilSourceAttachQuality;
}

export default function MidnightOilSourceAttachQualityPanel({
  composeFn = composeMidnightOilSourceAttachQuality,
}: MidnightOilSourceAttachQualityPanelProps) {
  const [minutes, setMinutes] = useState("120");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilSourceAttachQualityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const work_minutes = Math.max(1, parseInt(minutes, 10) || 120);
      setResult(
        composeFn({
          operator_id: "op-demo",
          work_minutes,
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
              external_id: "arxiv:2001.08361",
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
    <div data-testid="midnight-oil-source-attach-quality-panel">
      <LemonCard
        title="Midnight Oil · unattended + source quality attach"
        className="midnight-oil-source-attach-quality-panel"
      >
        <p className="text-sm opacity-80" data-testid="mosaq-blurb">
          Time + goals + price ceiling with arxiv/substack HTML sources under
          quality gate. Pure — never launches workers or scrapes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="mosaq-minutes"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mosaq-ack"
            />
            <span>operator_ack / unattended_ack / spend_consent</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="mosaq-compose"
          >
            Compose MO + sources
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="mosaq-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="mosaq-result">
            <p data-testid="mosaq-summary">
              {formatMidnightOilSourceAttachQualitySummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                mo_ready=
                {String(result.mo_unattended.unattended_package_ready)}
              </li>
              <li>
                source_ready={String(result.source_quality.pack_ready)}
              </li>
              <li>
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
