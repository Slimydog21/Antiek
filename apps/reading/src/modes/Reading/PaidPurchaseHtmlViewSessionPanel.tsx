/**
 * PaidPurchaseHtmlViewSessionPanel — marketplace gate → HTML reader session.
 *
 * Free-file. purchase/charge/host/pdf/store always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composePaidPurchaseHtmlViewSession,
  formatPaidPurchaseHtmlViewSessionSummary,
  type PaidPurchaseHtmlViewSessionCompose,
} from "../../api/paidPurchaseHtmlViewSessionCompose";

export interface PaidPurchaseHtmlViewSessionPanelProps {
  composeFn?: typeof composePaidPurchaseHtmlViewSession;
}

export default function PaidPurchaseHtmlViewSessionPanel({
  composeFn = composePaidPurchaseHtmlViewSession,
}: PaidPurchaseHtmlViewSessionPanelProps) {
  const [title, setTitle] = useState("Deep Learning Book");
  const [freeAvail, setFreeAvail] = useState<"true" | "false">("false");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<PaidPurchaseHtmlViewSessionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const free = freeAvail === "true";
      setResult(
        composeFn({
          session_id: "sess-1",
          asset_id: "book-1",
          title: title.trim(),
          account_id: "acct-1",
          free_copy_available: free,
          free_html_projection_sha: free ? "sha-free-demo" : null,
          purchase_html_projection_sha: free ? null : "sha-paid-demo",
          port_requested: true,
          purchase_ack: !free,
          list_price_usd: free ? null : 15,
          approved_spend_usd: free ? null : 20,
          remaining_budget_usd: free ? null : 100,
          operator_ack: ack,
          view_requested: true,
          twin_bound: true,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="paid-purchase-html-view-session-panel">
      <LemonCard
        title="Reading · paid/free gate → HTML view session"
        className="paid-purchase-html-view-session-panel"
      >
        <p className="text-sm opacity-80" data-testid="pphvs-blurb">
          Free-first marketplace gate then HTML-native reading session. Never
          charges or opens PDF as primary view.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="pphvs-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Free available</span>
            <select
              value={freeAvail}
              onChange={(e) =>
                setFreeAvail(e.target.value as "true" | "false")
              }
              data-testid="pphvs-free"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false (paid path)</option>
              <option value="true">true (free HTML)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="pphvs-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="pphvs-compose"
          >
            Compose purchase → HTML session
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="pphvs-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="pphvs-result"
            >
              <div data-testid="pphvs-ready">
                session_package_ready={String(result.session_package_ready)}
              </div>
              <div data-testid="pphvs-charge">
                charge_executed={String(result.charge_executed)}
              </div>
              <div data-testid="pphvs-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="pphvs-hosted">
                hosted={String(result.hosted)}
              </div>
              <div data-testid="pphvs-summary">
                {formatPaidPurchaseHtmlViewSessionSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
