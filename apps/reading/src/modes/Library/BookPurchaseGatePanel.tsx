/**
 * BookPurchaseGatePanel — free-before-buy marketplace honesty UI.
 *
 * Free-file under Library/. Does not charge or port books.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatPurchaseGateSummary,
  parsePurchaseGateDecision,
  postPurchaseGate,
  type PurchaseGateDecision,
} from "../../api/bookPurchaseGate";

export interface BookPurchaseGatePanelProps {
  gateFn?: (
    req: Parameters<typeof postPurchaseGate>[0],
  ) => Promise<PurchaseGateDecision | unknown>;
  initialTitle?: string;
  initialAuthor?: string;
  /** From free-copy preflight; required unless skip. */
  freeCopyFreelyAvailable?: boolean | null;
}

export default function BookPurchaseGatePanel({
  gateFn = postPurchaseGate,
  initialTitle = "",
  initialAuthor = "",
  freeCopyFreelyAvailable = null,
}: BookPurchaseGatePanelProps) {
  const [title, setTitle] = useState(initialTitle);
  const [author, setAuthor] = useState(initialAuthor);
  const [skip, setSkip] = useState(false);
  const [skipAck, setSkipAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PurchaseGateDecision | null>(null);

  async function onEvaluate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const raw = await gateFn({
        title: title.trim(),
        author: author.trim() || null,
        skip_free_copy: skip,
        operator_skip_acknowledged: skip ? skipAck : null,
        free_copy_preflight:
          skip || freeCopyFreelyAvailable === null
            ? skip
              ? null
              : undefined
            : { freely_available: freeCopyFreelyAvailable },
      });
      setResult(parsePurchaseGateDecision(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="book-purchase-gate-panel">
      <LemonCard title="Purchase gate (free-before-buy)" className="book-purchase-gate-panel">
        <p className="text-sm opacity-80" data-testid="book-purchase-gate-blurb">
          Allow purchase intent only after free-copy preflight finds none (or
          explicit operator skip). This panel never executes a charge.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="bpg-title"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Author (optional)</span>
            <LemonInput
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              data-testid="bpg-author"
              disabled={busy}
            />
          </label>
          <div className="text-xs opacity-70" data-testid="bpg-free-status">
            free_copy_freely_available=
            {freeCopyFreelyAvailable === null
              ? "null"
              : String(freeCopyFreelyAvailable)}
          </div>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={skip}
              onChange={(e) => setSkip(e.target.checked)}
              data-testid="bpg-skip"
              disabled={busy}
            />
            Skip free-copy preflight
          </label>
          {skip ? (
            <label className="text-sm flex items-center gap-2">
              <input
                type="checkbox"
                checked={skipAck}
                onChange={(e) => setSkipAck(e.target.checked)}
                data-testid="bpg-skip-ack"
                disabled={busy}
              />
              I acknowledge skipping free-copy search
            </label>
          ) : null}
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onEvaluate()}
            data-testid="bpg-evaluate"
          >
            {busy ? "Evaluating…" : "Evaluate purchase gate"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="bpg-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="bpg-result" className="text-sm flex flex-col gap-1">
              <div data-testid="bpg-summary">
                {formatPurchaseGateSummary(result)}
              </div>
              <div data-testid="bpg-executed">
                purchase_executed={String(result.purchase_executed)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
