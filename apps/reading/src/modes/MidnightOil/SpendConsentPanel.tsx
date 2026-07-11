/**
 * SpendConsentPanel — display operator MO spend consent receipt (view only).
 *
 * Free-file. Does not issue/claim receipts, hold keys, or authorize spend.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  formatConsentReceiptSummary,
  isConsentExpired,
  parseConsentReceiptView,
  type ConsentReceiptView,
} from "../../api/spendConsentView";

export interface SpendConsentPanelProps {
  /** Injectable receipt loader/parser input. */
  loadFn?: () => Promise<unknown>;
  /** Optional static receipt (re-parsed on every receipt prop change). */
  receipt?: unknown;
  nowMs?: number;
}

export default function SpendConsentPanel({
  loadFn,
  receipt = null,
  nowMs = Date.now(),
}: SpendConsentPanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<ConsentReceiptView | null>(null);

  // Re-parse static receipt whenever the prop changes (no stale prior view).
  const staticParsed = useMemo(() => {
    if (receipt == null || loadFn) {
      return { view: null as ConsentReceiptView | null, error: null as string | null };
    }
    try {
      return { view: parseConsentReceiptView(receipt), error: null as string | null };
    } catch (e) {
      return {
        view: null as ConsentReceiptView | null,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  }, [receipt, loadFn]);

  async function onLoad() {
    if (!loadFn) return;
    setBusy(true);
    setError(null);
    setLoaded(null);
    try {
      const raw = await loadFn();
      setLoaded(parseConsentReceiptView(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const shown = loadFn ? loaded : staticParsed.view;
  const shownError = loadFn ? error : staticParsed.error;

  return (
    <div data-testid="spend-consent-panel">
      <LemonCard title="Spend consent receipt" className="spend-consent-panel">
        <p className="text-sm opacity-80" data-testid="spend-consent-blurb">
          Display-only view of an operator spend consent receipt. Signature is
          never verified here; issuing/claiming requires the server substrate.
        </p>
        {loadFn ? (
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onLoad()}
            data-testid="spend-consent-load"
            className="mt-2"
          >
            {busy ? "Loading…" : "Load receipt"}
          </LemonButton>
        ) : null}
        {shownError ? (
          <div className="text-sm text-danger mt-2" data-testid="spend-consent-error">
            {shownError}
          </div>
        ) : null}
        {shown ? (
          <div data-testid="spend-consent-result" className="mt-3 text-sm flex flex-col gap-1">
            <div data-testid="spend-consent-summary">
              {formatConsentReceiptSummary(shown)}
            </div>
            <div data-testid="spend-consent-sig">
              signature_verified={String(shown.signature_verified)}; authority=
              {shown.authority}
            </div>
            <div data-testid="spend-consent-expired">
              expired={String(isConsentExpired(shown, nowMs))}
            </div>
          </div>
        ) : null}
      </LemonCard>
    </div>
  );
}
