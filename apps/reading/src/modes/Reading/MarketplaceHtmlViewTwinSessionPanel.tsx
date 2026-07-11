/**
 * MarketplaceHtmlViewTwinSessionPanel — free/paid → HTML + twin UI.
 *
 * Free-file. purchase/charge/host/pdf/twin_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMarketplaceHtmlViewTwinSession,
  formatMarketplaceHtmlViewTwinSessionSummary,
  type MarketplaceHtmlViewTwinSessionCompose,
} from "../../api/marketplaceHtmlViewTwinSessionCompose";

export interface MarketplaceHtmlViewTwinSessionPanelProps {
  composeFn?: typeof composeMarketplaceHtmlViewTwinSession;
}

export default function MarketplaceHtmlViewTwinSessionPanel({
  composeFn = composeMarketplaceHtmlViewTwinSession,
}: MarketplaceHtmlViewTwinSessionPanelProps) {
  const [title, setTitle] = useState("Deep Learning Book");
  const [freeAvail, setFreeAvail] = useState<"true" | "false">("false");
  const [ack, setAck] = useState(true);
  const [includeTwin, setIncludeTwin] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceHtmlViewTwinSessionCompose | null>(null);

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
          include_twin_feed: includeTwin,
          mark_for_prompt_context: true,
          twin_findings: [
            {
              source_id: "q1",
              body: "What is the core thesis?",
              kind: "question",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-html-view-twin-session-panel">
      <LemonCard
        title="Reading · marketplace → HTML + twin"
        className="marketplace-html-view-twin-session-panel"
      >
        <p className="text-sm opacity-80" data-testid="mhvts-blurb">
          Free-first or paid digital book into HTML-native reading with twin
          note substrate. Pure — never charges or writes twins.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="mhvts-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Free available</span>
            <select
              value={freeAvail}
              onChange={(e) =>
                setFreeAvail(e.target.value as "true" | "false")
              }
              data-testid="mhvts-free"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false (paid path)</option>
              <option value="true">true (free HTML)</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeTwin}
              onChange={(e) => setIncludeTwin(e.target.checked)}
              data-testid="mhvts-twin"
            />
            <span>include_twin_feed</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mhvts-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mhvts-compose"
          >
            Compose marketplace HTML + twin session
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="mhvts-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="mhvts-result"
            >
              <div data-testid="mhvts-ready">
                session_ready={String(result.session_ready)}
              </div>
              <div data-testid="mhvts-charge">
                charge_executed={String(result.charge_executed)}
              </div>
              <div data-testid="mhvts-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="mhvts-twin-w">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="mhvts-summary">
                {formatMarketplaceHtmlViewTwinSessionSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
