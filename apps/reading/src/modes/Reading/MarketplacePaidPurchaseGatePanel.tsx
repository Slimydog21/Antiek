/**
 * MarketplacePaidPurchaseGatePanel — free-first paid purchase gate UI.
 *
 * Free-file. purchase_executed, charge_executed, hosted, pdf_view_authorized
 * always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMarketplacePaidPurchaseGate,
  formatMarketplacePaidPurchaseGateSummary,
  type MarketplacePaidPurchaseGateCompose,
} from "../../api/marketplacePaidPurchaseGateCompose";

export interface MarketplacePaidPurchaseGatePanelProps {
  composeFn?: typeof composeMarketplacePaidPurchaseGate;
}

export default function MarketplacePaidPurchaseGatePanel({
  composeFn = composeMarketplacePaidPurchaseGate,
}: MarketplacePaidPurchaseGatePanelProps) {
  const [title, setTitle] = useState("Deep Learning Book");
  const [account, setAccount] = useState("acct-1");
  const [freeAvail, setFreeAvail] = useState<"true" | "false" | "unknown">(
    "false",
  );
  const [listPrice, setListPrice] = useState("15");
  const [approved, setApproved] = useState("20");
  const [remaining, setRemaining] = useState("100");
  const [purchaseAck, setPurchaseAck] = useState(true);
  const [portReq, setPortReq] = useState(true);
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplacePaidPurchaseGateCompose | null>(null);

  function parseMoney(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) throw new Error("money fields must be finite");
    return n;
  }

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const free_copy_available =
        freeAvail === "unknown" ? null : freeAvail === "true";
      setResult(
        composeFn({
          title: title.trim(),
          account_id: account.trim(),
          free_copy_available,
          free_html_projection_sha:
            free_copy_available === true ? "sha-free-demo" : null,
          purchase_html_projection_sha:
            free_copy_available === false ? "sha-paid-demo" : null,
          port_requested: portReq,
          purchase_ack: purchaseAck,
          list_price_usd: parseMoney(listPrice),
          approved_spend_usd: parseMoney(approved),
          remaining_budget_usd: parseMoney(remaining),
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-paid-purchase-gate-panel">
      <LemonCard
        title="Marketplace · paid purchase gate (HTML port)"
        className="marketplace-paid-purchase-gate-panel"
      >
        <p className="text-sm opacity-80" data-testid="mppg-blurb">
          Free-first: buy only when free unavailable, under approved spend and
          remaining budget. Pure — purchase/charge/host stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="mppg-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Account</span>
            <LemonInput
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              data-testid="mppg-account"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Free copy available</span>
            <select
              value={freeAvail}
              onChange={(e) =>
                setFreeAvail(e.target.value as "true" | "false" | "unknown")
              }
              data-testid="mppg-free"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false (paid path)</option>
              <option value="true">true (prefer free)</option>
              <option value="unknown">unknown (null)</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>List price USD</span>
            <LemonInput
              value={listPrice}
              onChange={(e) => setListPrice(e.target.value)}
              data-testid="mppg-list"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved spend USD</span>
            <LemonInput
              value={approved}
              onChange={(e) => setApproved(e.target.value)}
              data-testid="mppg-approved"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Remaining budget USD</span>
            <LemonInput
              value={remaining}
              onChange={(e) => setRemaining(e.target.value)}
              data-testid="mppg-remaining"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={purchaseAck}
              onChange={(e) => setPurchaseAck(e.target.checked)}
              data-testid="mppg-purchase-ack"
            />
            <span>purchase_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={portReq}
              onChange={(e) => setPortReq(e.target.checked)}
              data-testid="mppg-port"
            />
            <span>port_requested</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mppg-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mppg-compose"
          >
            Compose paid purchase gate
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="mppg-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="mppg-result"
            >
              <div data-testid="mppg-gate">
                gate_ready={String(result.gate_ready)}
              </div>
              <div data-testid="mppg-purchase">
                purchase_ready={String(result.purchase_ready)}
              </div>
              <div data-testid="mppg-would">
                would_exceed_budget=
                {result.would_exceed_budget === null
                  ? "null"
                  : String(result.would_exceed_budget)}
              </div>
              <div data-testid="mppg-exec">
                purchase_executed={String(result.purchase_executed)}
              </div>
              <div data-testid="mppg-charge">
                charge_executed={String(result.charge_executed)}
              </div>
              <div data-testid="mppg-hosted">
                hosted={String(result.hosted)}
              </div>
              <div data-testid="mppg-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="mppg-summary">
                {formatMarketplacePaidPurchaseGateSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
