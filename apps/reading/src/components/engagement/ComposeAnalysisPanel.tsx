/**
 * ComposeAnalysisPanel — same-parent twin → HTML analysis draft UI.
 *
 * Consumes POST /twins/compose (PR #790). Cross-parent twins are rejected by
 * the API. Output is a provisional HTML analysis draft only — does not
 * finalize into the parent asset or dispatch models.
 *
 * Free-file: does not own Reading/index, Settings/index, App.tsx, or rrv-712.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  formatComposeMeta,
  formatHtmlPreview,
  parseComposeAnalysisResult,
  postComposeAnalysis,
  type ComposeAnalysisResult,
} from "../../api/twinCompose";

export interface ComposeAnalysisPanelProps {
  /**
   * Injectable compose builder. Return value is re-validated with
   * parseComposeAnalysisResult so empty html cannot surface as success even
   * when the injector bypasses postComposeAnalysis.
   */
  composeFn?: (
    req: Parameters<typeof postComposeAnalysis>[0],
  ) => Promise<ComposeAnalysisResult | unknown>;
  initialTwinIds?: string;
  initialTitle?: string;
  initialParentAssetId?: string;
}

function parseTwinIds(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function ComposeAnalysisPanel({
  composeFn = postComposeAnalysis,
  initialTwinIds = "",
  initialTitle = "Combined analysis",
  initialParentAssetId = "",
}: ComposeAnalysisPanelProps) {
  const [twinIdsRaw, setTwinIdsRaw] = useState(initialTwinIds);
  const [title, setTitle] = useState(initialTitle);
  const [parentAssetId, setParentAssetId] = useState(initialParentAssetId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComposeAnalysisResult | null>(null);

  const twinIds = useMemo(() => parseTwinIds(twinIdsRaw), [twinIdsRaw]);

  async function onCompose() {
    setBusy(true);
    setError(null);
    try {
      const raw = await composeFn({
        twin_ids: twinIds,
        title,
        parent_asset_id: parentAssetId.trim() || null,
      });
      // Fail closed at panel boundary (covers injectable stubs).
      const body = parseComposeAnalysisResult(raw);
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="compose-analysis-panel">
      <LemonCard title="Compose twin analysis" className="compose-analysis-panel">
        <p className="text-sm opacity-80" data-testid="compose-analysis-blurb">
          Merge completed twin note-taker documents that share one parent asset
          into a single HTML analysis draft. Cross-parent compose is rejected.
          This panel does not finalize into the parent or dispatch models.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Twin ids (comma or space separated)</span>
            <LemonInput
              value={twinIdsRaw}
              onChange={(e) => setTwinIdsRaw(e.target.value)}
              placeholder="twin-a, twin-b"
              data-testid="compose-analysis-twin-ids"
              aria-label="Twin ids"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Draft title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Combined analysis"
              data-testid="compose-analysis-title"
              aria-label="Analysis title"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id (optional pin; must match twins)</span>
            <LemonInput
              value={parentAssetId}
              onChange={(e) => setParentAssetId(e.target.value)}
              placeholder="asset-…"
              data-testid="compose-analysis-parent"
              aria-label="Parent asset id"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onCompose()}
            data-testid="compose-analysis-run"
          >
            {busy ? "Composing…" : "Compose HTML analysis"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="compose-analysis-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="compose-analysis-result" className="flex flex-col gap-2">
              <div data-testid="compose-analysis-meta">
                {formatComposeMeta(result)}
              </div>
              <div data-testid="compose-analysis-twins">
                Twins: {result.twin_ids.join(", ")}
              </div>
              <div data-testid="compose-analysis-title-echo">
                Title: {result.title}
              </div>
              <pre
                className="max-h-56 overflow-auto rounded border border-border bg-bg-light p-2 text-xs whitespace-pre-wrap"
                data-testid="compose-analysis-html"
              >
                {result.html}
              </pre>
              <div className="text-xs opacity-70" data-testid="compose-analysis-preview">
                Preview: {formatHtmlPreview(result.html)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
