/**
 * MarketplaceFreeBeforeBuyHtmlPortPanel — free-first HTML port intent.
 *
 * Free-file. purchase_executed, hosted, pdf_view_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  formatMarketplaceFreeBeforeBuyHtmlPortSummary,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
} from "../../api/marketplaceFreeBeforeBuyHtmlPortCompose";

export interface MarketplaceFreeBeforeBuyHtmlPortPanelProps {
  composeFn?: typeof composeMarketplaceFreeBeforeBuyHtmlPort;
}

export default function MarketplaceFreeBeforeBuyHtmlPortPanel({
  composeFn = composeMarketplaceFreeBeforeBuyHtmlPort,
}: MarketplaceFreeBeforeBuyHtmlPortPanelProps) {
  const [title, setTitle] = useState("Deep Learning");
  const [account, setAccount] = useState("acct-1");
  const [freeAvail, setFreeAvail] = useState<"true" | "false" | "null">("true");
  const [freeSha, setFreeSha] = useState("sha-free-1");
  const [purchaseAck, setPurchaseAck] = useState(false);
  const [portReq, setPortReq] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceFreeBeforeBuyHtmlPortCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const free_copy_available =
        freeAvail === "null" ? null : freeAvail === "true";
      setResult(
        composeFn({
          title: title.trim(),
          account_id: account.trim(),
          free_copy_available,
          free_html_projection_sha: freeSha.trim() || null,
          purchase_ack: purchaseAck,
          port_requested: portReq,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-free-before-buy-html-port-panel">
      <LemonCard
        title="Marketplace · free-before-buy HTML port"
        className="marketplace-free-before-buy-html-port-panel"
      >
        <p className="text-sm opacity-80" data-testid="mfbhp-blurb">
          Free copy first; purchase only when free unavailable; port as HTML
          into account. Pure — purchase_executed, hosted, pdf_view_authorized
          stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="mfbhp-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Account id</span>
            <LemonInput
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              data-testid="mfbhp-account"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>free_copy_available</span>
            <select
              value={freeAvail}
              onChange={(e) =>
                setFreeAvail(e.target.value as "true" | "false" | "null")
              }
              data-testid="mfbhp-free"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="true">true</option>
              <option value="false">false</option>
              <option value="null">null</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Free HTML projection sha</span>
            <LemonInput
              value={freeSha}
              onChange={(e) => setFreeSha(e.target.value)}
              data-testid="mfbhp-sha"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={purchaseAck}
              onChange={(e) => setPurchaseAck(e.target.checked)}
              data-testid="mfbhp-purchase-ack"
            />
            <span>purchase_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={portReq}
              onChange={(e) => setPortReq(e.target.checked)}
              data-testid="mfbhp-port"
            />
            <span>port_requested</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mfbhp-compose"
          >
            Compose free-before-buy port
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="mfbhp-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="mfbhp-result"
            >
              <div data-testid="mfbhp-path">path={result.path}</div>
              <div data-testid="mfbhp-ready">
                port_ready={String(result.port_ready)}
              </div>
              <div data-testid="mfbhp-purchase">
                purchase_executed={String(result.purchase_executed)}
              </div>
              <div data-testid="mfbhp-hosted">
                hosted={String(result.hosted)}
              </div>
              <div data-testid="mfbhp-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="mfbhp-summary">
                {formatMarketplaceFreeBeforeBuyHtmlPortSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
