/**
 * HtmlHostPanel - HTML-native book host port UI (advisory).
 *
 * Free-file under Library/. Does not convert PDFs or charge purchases.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatHtmlHostSummary,
  parseHtmlHostReceipt,
  postHtmlHostEvaluate,
  type HtmlHostReceipt,
} from "../../api/htmlHost";

export interface HtmlHostPanelProps {
  evaluateFn?: (
    req: Parameters<typeof postHtmlHostEvaluate>[0],
  ) => Promise<HtmlHostReceipt | unknown>;
  initialTitle?: string;
  freeCopyFreelyAvailable?: boolean | null;
  purchaseIntentAllowed?: boolean | null;
  htmlProjectionReady?: boolean;
  htmlSha256?: string;
  htmlBytes?: number | null;
}

export default function HtmlHostPanel({
  evaluateFn = postHtmlHostEvaluate,
  initialTitle = "",
  freeCopyFreelyAvailable = null,
  purchaseIntentAllowed = null,
  htmlProjectionReady = false,
  htmlSha256 = "",
  htmlBytes = null,
}: HtmlHostPanelProps) {
  const [title, setTitle] = useState(initialTitle);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HtmlHostReceipt | null>(null);

  async function onEvaluate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const raw = await evaluateFn({
        title: title.trim(),
        free_copy_preflight:
          freeCopyFreelyAvailable === null
            ? null
            : { freely_available: freeCopyFreelyAvailable },
        purchase_gate:
          purchaseIntentAllowed === null
            ? null
            : {
                purchase_intent_allowed: purchaseIntentAllowed,
                purchase_executed: false,
              },
        html_projection: {
          ready: htmlProjectionReady,
          html_sha256: htmlSha256.trim() || null,
          html_bytes: htmlBytes,
        },
      });
      setResult(parseHtmlHostReceipt(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="html-host-panel">
      <LemonCard title="HTML host port" className="html-host-panel">
        <p className="text-sm opacity-80" data-testid="html-host-blurb">
          Host a book as HTML in your Antiek account after free-copy or allowed
          purchase intent. Requires a ready HTML projection hash - never invents
          HTML from PDF.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="html-host-title"
              disabled={busy}
            />
          </label>
          <div className="text-xs opacity-70" data-testid="html-host-inputs">
            free={String(freeCopyFreelyAvailable)}; purchase=
            {String(purchaseIntentAllowed)}; html_ready=
            {String(htmlProjectionReady)}
          </div>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onEvaluate()}
            data-testid="html-host-evaluate"
          >
            {busy ? "Evaluating…" : "Evaluate HTML host"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="html-host-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="html-host-result" className="text-sm flex flex-col gap-1">
              <div data-testid="html-host-summary">
                {formatHtmlHostSummary(result)}
              </div>
              <div data-testid="html-host-hosted">
                hosted={String(result.hosted)}; purchase_executed=
                {String(result.purchase_executed)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
