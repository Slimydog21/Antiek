/**
 * ReadingResearchHtmlParityComposePanel - reading↔research HTML parity.
 *
 * Free-file. PDF never primary; never invents projection sha.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeReadingResearchHtmlParity,
  formatReadingResearchHtmlParitySummary,
  type ReadingResearchHtmlParityCompose,
} from "../../api/readingResearchHtmlParityCompose";

export interface ReadingResearchHtmlParityComposePanelProps {
  composeFn?: typeof composeReadingResearchHtmlParity;
}

export default function ReadingResearchHtmlParityComposePanel({
  composeFn = composeReadingResearchHtmlParity,
}: ReadingResearchHtmlParityComposePanelProps) {
  const [assetId, setAssetId] = useState("asset-1");
  const [readSha, setReadSha] = useState("sha-abc");
  const [researchSha, setResearchSha] = useState("sha-abc");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ReadingResearchHtmlParityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const rSha = readSha.trim() || null;
      const sSha = researchSha.trim() || null;
      setResult(
        composeFn({
          reading: {
            asset_id: assetId,
            asset_kind: "book",
            source_format: rSha ? "html" : "pdf",
            html_projection_sha: rSha,
          },
          research: {
            asset_id: assetId,
            asset_kind: "research",
            source_format: sSha ? "markdown" : "pdf",
            html_projection_sha: sSha,
          },
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="reading-research-html-parity-compose-panel">
      <LemonCard
        title="Reading ↔ research HTML parity"
        className="reading-research-html-parity-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="rrhp-blurb">
          Confirm reading and research share the HTML-native view path. Pure
          compose — pdf_primary stays false; never invents projection sha.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Asset id</span>
            <LemonInput
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              data-testid="rrhp-asset"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Reading HTML projection sha (blank = none)</span>
            <LemonInput
              value={readSha}
              onChange={(e) => setReadSha(e.target.value)}
              data-testid="rrhp-read-sha"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Research HTML projection sha (blank = none)</span>
            <LemonInput
              value={researchSha}
              onChange={(e) => setResearchSha(e.target.value)}
              data-testid="rrhp-research-sha"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rrhp-compose"
          >
            Compose parity
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rrhp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="rrhp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="rrhp-summary">
                {formatReadingResearchHtmlParitySummary(result)}
              </div>
              <div data-testid="rrhp-parity">
                parity_ready={String(result.parity_ready)}
              </div>
              <div data-testid="rrhp-pdf">
                pdf_primary={String(result.pdf_primary)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
