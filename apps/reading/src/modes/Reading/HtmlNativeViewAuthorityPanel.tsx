/**
 * HtmlNativeViewAuthorityPanel - decide HTML primary human view for an asset.
 *
 * Free-file. Never invents ready projection sha.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  evaluateHtmlNativeViewAuthority,
  formatHtmlViewSummary,
  type AssetKind,
  type HtmlNativeViewAuthorityDecision,
  type SourceFormat,
} from "../../api/htmlNativeViewAuthority";

export interface HtmlNativeViewAuthorityPanelProps {
  evaluateFn?: typeof evaluateHtmlNativeViewAuthority;
  initialAssetId?: string;
}

export default function HtmlNativeViewAuthorityPanel({
  evaluateFn = evaluateHtmlNativeViewAuthority,
  initialAssetId = "",
}: HtmlNativeViewAuthorityPanelProps) {
  const [assetId, setAssetId] = useState(initialAssetId);
  const [kind, setKind] = useState<AssetKind>("book");
  const [format, setFormat] = useState<SourceFormat>("pdf");
  const [sha, setSha] = useState("");
  const [preferHtml, setPreferHtml] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeViewAuthorityDecision | null>(null);

  function onEval() {
    setError(null);
    setResult(null);
    try {
      setResult(
        evaluateFn({
          asset_id: assetId.trim(),
          asset_kind: kind,
          source_format: format,
          html_projection_sha: sha.trim() || null,
          prefer_html: preferHtml,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="html-native-view-authority-panel">
      <LemonCard
        title="HTML-native view authority"
        className="html-native-view-authority-panel"
      >
        <p className="text-sm opacity-80" data-testid="hnva-blurb">
          Every human-viewable asset uses HTML as the primary surface. This
          panel decides authority only — never invents a ready projection sha.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Asset id</span>
            <LemonInput
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              data-testid="hnva-asset"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Asset kind</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as AssetKind)}
              data-testid="hnva-kind"
              className="border border-border rounded px-2 py-1"
            >
              <option value="book">book</option>
              <option value="research">research</option>
              <option value="twin">twin</option>
              <option value="analysis">analysis</option>
              <option value="paper">paper</option>
              <option value="other">other</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source format</span>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as SourceFormat)}
              data-testid="hnva-format"
              className="border border-border rounded px-2 py-1"
            >
              <option value="pdf">pdf</option>
              <option value="html">html</option>
              <option value="epub">epub</option>
              <option value="markdown">markdown</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>HTML projection sha (blank = not ready)</span>
            <LemonInput
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              data-testid="hnva-sha"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={preferHtml}
              onChange={(e) => setPreferHtml(e.target.checked)}
              data-testid="hnva-prefer"
            />
            prefer_html
          </label>
          <LemonButton
            variant="primary"
            onClick={onEval}
            data-testid="hnva-run"
          >
            Evaluate HTML view authority
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="hnva-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="hnva-result" className="text-sm flex flex-col gap-1">
              <div data-testid="hnva-summary">{formatHtmlViewSummary(result)}</div>
              <div data-testid="hnva-human">
                human_viewable_html={String(result.human_viewable_html)}
              </div>
              <div data-testid="hnva-primary">
                primary_format={result.primary_format}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
