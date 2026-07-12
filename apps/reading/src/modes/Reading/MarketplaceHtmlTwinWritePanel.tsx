/**
 * MarketplaceHtmlTwinWritePanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMarketplaceHtmlTwinWrite,
  formatMarketplaceHtmlTwinWriteSummary,
  type MarketplaceHtmlTwinWriteCompose,
} from "../../api/marketplaceHtmlTwinWriteCompose";

export default function MarketplaceHtmlTwinWritePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceHtmlTwinWriteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeMarketplaceHtmlTwinWrite({
          session_id: "sess-demo",
          asset_id: "book-demo",
          draft_id: "draft-demo",
          title: "Scaling Laws",
          account_id: "acct-demo",
          free_copy_available: true,
          free_html_projection_sha: "sha-free",
          port_requested: true,
          purchase_ack: false,
          list_price_usd: 10,
          approved_spend_usd: 20,
          remaining_budget_usd: 50,
          operator_ack: ack,
          view_requested: true,
          twin_findings: [
            {
              source_id: "q1",
              body: "What is the core thesis?",
              kind: "question",
            },
            {
              source_id: "i1",
              body: "Power-law scaling insight",
              kind: "insight",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-html-twin-write-panel">
      <LemonCard title="Marketplace · HTML book + twin → write">
        <p className="text-sm opacity-80">
          Free/paid HTML book session with twin substrate folding into write
          draft. Pure — no charge, no PDF, no live host.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="mhtw-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="mhtw-compose"
        >
          Compose marketplace → write
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="mhtw-result">
            <p>{formatMarketplaceHtmlTwinWriteSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>pdf_view={String(result.pdf_view_authorized)}</li>
              <li>draft_written={String(result.draft_written)}</li>
              <li>charge_executed={String(result.charge_executed)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
