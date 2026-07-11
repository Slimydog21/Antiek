/**
 * HtmlNativeViewSessionAuthorityPanel — HTML-only view doctrine pack.
 *
 * Free-file. pdf_view/pdf_primary/store always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHtmlNativeViewSessionAuthority,
  formatHtmlNativeViewSessionAuthoritySummary,
  type HtmlNativeViewSessionAuthorityCompose,
} from "../../api/htmlNativeViewSessionAuthorityCompose";

export interface HtmlNativeViewSessionAuthorityPanelProps {
  composeFn?: typeof composeHtmlNativeViewSessionAuthority;
}

export default function HtmlNativeViewSessionAuthorityPanel({
  composeFn = composeHtmlNativeViewSessionAuthority,
}: HtmlNativeViewSessionAuthorityPanelProps) {
  const [sha, setSha] = useState("sha-demo-html");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeViewSessionAuthorityCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          asset_id: "asset-demo",
          html_projection_sha: sha.trim() || null,
          view_requested: true,
          twin_bound: true,
          twin_substrate_ready: true,
          claimed_format: "html",
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="html-native-view-session-authority-panel">
      <LemonCard
        title="Reading/Research · HTML-native view authority"
        className="html-native-view-session-authority-panel"
      >
        <p className="text-sm opacity-80" data-testid="hnvsa-blurb">
          Open information assets only as HTML with reading/research parity.
          Pure — PDF never primary; store never mutated.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>HTML projection sha</span>
            <LemonInput
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              data-testid="hnvsa-sha"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="hnvsa-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="hnvsa-compose"
          >
            Compose HTML view pack
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="hnvsa-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="hnvsa-result">
            <p data-testid="hnvsa-summary">
              {formatHtmlNativeViewSessionAuthoritySummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </li>
              <li>pdf_primary={String(result.pdf_primary)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
