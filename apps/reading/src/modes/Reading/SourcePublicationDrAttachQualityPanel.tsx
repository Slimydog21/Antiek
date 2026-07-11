/**
 * SourcePublicationDrAttachQualityPanel — arxiv/substack DR attach pack.
 *
 * Free-file. remote_fetched/pdf/dispatch always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSourcePublicationDrAttachQuality,
  formatSourcePublicationDrAttachQualitySummary,
  type SourcePublicationDrAttachQualityCompose,
} from "../../api/sourcePublicationDrAttachQualityCompose";

export interface SourcePublicationDrAttachQualityPanelProps {
  composeFn?: typeof composeSourcePublicationDrAttachQuality;
}

export default function SourcePublicationDrAttachQualityPanel({
  composeFn = composeSourcePublicationDrAttachQuality,
}: SourcePublicationDrAttachQualityPanelProps) {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourcePublicationDrAttachQualityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          requested_families: ["arxiv", "substack"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo arXiv paper",
              external_id: "arxiv:2001.08361",
              html_fragment: "<article>HTML projection</article>",
            },
            {
              source_id: "sub-demo",
              family: "substack",
              title: "Demo Substack essay",
              html_fragment: "<article>essay body</article>",
            },
          ],
          quality_overall: 0.82,
          quality_floor: 0.7,
          would_exceed: false,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="source-publication-dr-attach-quality-panel">
      <LemonCard
        title="Research · arXiv/Substack attach + quality"
        className="source-publication-dr-attach-quality-panel"
      >
        <p className="text-sm opacity-80" data-testid="spdaq-blurb">
          Attach knowledge-dense publications as HTML-native sources with
          citation pack and quality/budget gate. Pure — never scrapes or
          dispatches.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="spdaq-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="spdaq-compose"
          >
            Compose source attach pack
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="spdaq-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="spdaq-result">
            <p data-testid="spdaq-summary">
              {formatSourcePublicationDrAttachQualitySummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
              <li>
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </li>
              <li>
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </li>
              <li>citations={result.citation_pack.citation_count}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
