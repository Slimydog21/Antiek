/**
 * HtmlPreferencePanel — HTML-native view preference decision UI.
 *
 * Consumes POST /assets/view-preference/decide via #806 client.
 * Free-file: does not own Reading/index or delete PdfViewer.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../lemon";
import {
  decideViewPreference,
  formatViewMode,
  type ViewPreferenceDecision,
} from "../../api/htmlPreference";

export interface HtmlPreferencePanelProps {
  decideFn?: typeof decideViewPreference;
  initialHtmlReady?: boolean;
  initialPdfAvailable?: boolean;
  initialRequireHtml?: boolean;
}

export default function HtmlPreferencePanel({
  decideFn = decideViewPreference,
  initialHtmlReady = true,
  initialPdfAvailable = true,
  initialRequireHtml = true,
}: HtmlPreferencePanelProps) {
  const [htmlReady, setHtmlReady] = useState(initialHtmlReady);
  const [pdfAvailable, setPdfAvailable] = useState(initialPdfAvailable);
  const [requireHtml, setRequireHtml] = useState(initialRequireHtml);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ViewPreferenceDecision | null>(null);

  async function onDecide() {
    setBusy(true);
    setError(null);
    try {
      const body = await decideFn({
        html_ready: htmlReady,
        pdf_available: pdfAvailable,
        require_html: requireHtml,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="html-preference-panel">
      <LemonCard title="HTML view preference" className="html-preference-panel">
        <p className="text-sm opacity-80" data-testid="html-preference-blurb">
          Prefer HTML-native assets over PDF when ready HTML exists. Policy can
          block PDF body when require_html is set.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={htmlReady}
              onChange={(e) => setHtmlReady(e.target.checked)}
              data-testid="html-preference-html-ready"
            />
            HTML ready
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={pdfAvailable}
              onChange={(e) => setPdfAvailable(e.target.checked)}
              data-testid="html-preference-pdf-available"
            />
            PDF available
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={requireHtml}
              onChange={(e) => setRequireHtml(e.target.checked)}
              data-testid="html-preference-require-html"
            />
            Require HTML (block PDF body when only PDF)
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onDecide()}
            data-testid="html-preference-decide"
          >
            {busy ? "Deciding…" : "Decide view mode"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="html-preference-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="html-preference-result" className="flex flex-col gap-1">
              <div data-testid="html-preference-mode">
                Mode: {formatViewMode(result.mode)}
              </div>
              <div data-testid="html-preference-preferred">
                Preferred: {result.preferred ? "yes" : "no"}
              </div>
              <div data-testid="html-preference-reason">Reason: {result.reason}</div>
              {result.notes?.length ? (
                <ul data-testid="html-preference-notes">
                  {result.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
