/**
 * HtmlAssetViewSessionPanel — HTML-native asset view session.
 *
 * Free-file. pdf_view_authorized and store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHtmlAssetViewSession,
  formatHtmlAssetViewSessionSummary,
  type HtmlAssetViewSessionCompose,
} from "../../api/htmlAssetViewSessionCompose";

export interface HtmlAssetViewSessionPanelProps {
  composeFn?: typeof composeHtmlAssetViewSession;
}

export default function HtmlAssetViewSessionPanel({
  composeFn = composeHtmlAssetViewSession,
}: HtmlAssetViewSessionPanelProps) {
  const [sessionId, setSessionId] = useState("vs-1");
  const [assetId, setAssetId] = useState("asset-1");
  const [sha, setSha] = useState("sha-html-1");
  const [viewReq, setViewReq] = useState(true);
  const [twinBound, setTwinBound] = useState(true);
  const [format, setFormat] = useState("html");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlAssetViewSessionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          asset_id: assetId.trim(),
          html_projection_sha: sha.trim() || null,
          view_requested: viewReq,
          twin_bound: twinBound,
          twin_substrate_ready: twinBound,
          claimed_format: format.trim() || null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="html-asset-view-session-panel">
      <LemonCard
        title="HTML asset view session"
        className="html-asset-view-session-panel"
      >
        <p className="text-sm opacity-80" data-testid="havs-blurb">
          Open any information asset as HTML with twin readiness. PDF is never
          primary — pdf_view_authorized stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="havs-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Asset id</span>
            <LemonInput
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              data-testid="havs-asset"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>HTML projection sha</span>
            <LemonInput
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              data-testid="havs-sha"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Claimed format</span>
            <LemonInput
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              data-testid="havs-format"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={viewReq}
              onChange={(e) => setViewReq(e.target.checked)}
              data-testid="havs-view"
            />
            <span>view_requested</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={twinBound}
              onChange={(e) => setTwinBound(e.target.checked)}
              data-testid="havs-twin"
            />
            <span>twin_bound</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="havs-compose"
          >
            Compose HTML view session
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="havs-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="havs-result"
            >
              <div data-testid="havs-ready">
                session_ready={String(result.session_ready)}
              </div>
              <div data-testid="havs-html">
                html_view_ready={String(result.html_view_ready)}
              </div>
              <div data-testid="havs-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="havs-summary">
                {formatHtmlAssetViewSessionSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
