/**
 * UnattendedLaunchGatePanel — evaluate dispatch readiness (not live spend).
 *
 * Free-file under MidnightOil/. Combines brief fields + consent receipt id +
 * operator approval. Never claims live_execution_authorized.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatLaunchGateSummary,
  parseLaunchGateDecision,
  postUnattendedLaunchGate,
  type LaunchGateDecision,
} from "../../api/unattendedLaunchGate";

export interface UnattendedLaunchGatePanelProps {
  gateFn?: (
    req: Parameters<typeof postUnattendedLaunchGate>[0],
  ) => Promise<LaunchGateDecision | unknown>;
  initialDurationMinutes?: number;
  initialGoals?: string;
  initialApprovedCeilingCents?: number;
  initialConsentReceiptId?: string;
  initialOperatorApproved?: boolean;
}

export default function UnattendedLaunchGatePanel({
  gateFn = postUnattendedLaunchGate,
  initialDurationMinutes = 60,
  initialGoals = "",
  initialApprovedCeilingCents = 0,
  initialConsentReceiptId = "",
  initialOperatorApproved = false,
}: UnattendedLaunchGatePanelProps) {
  const [duration, setDuration] = useState(String(initialDurationMinutes));
  const [goalsRaw, setGoalsRaw] = useState(initialGoals);
  const [approved, setApproved] = useState(String(initialApprovedCeilingCents));
  const [receipt, setReceipt] = useState(initialConsentReceiptId);
  const [operatorApproved, setOperatorApproved] = useState(
    initialOperatorApproved,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LaunchGateDecision | null>(null);

  async function onEvaluate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (typeof operatorApproved !== "boolean") {
        throw new Error("operator_approved must be an explicit boolean");
      }
      const goals = goalsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const raw = await gateFn({
        operator_approved: operatorApproved,
        consent_receipt_id: receipt.trim() || null,
        duration_minutes: Number(duration),
        goals,
        approved_ceiling_cents: Number(approved),
      });
      setResult(parseLaunchGateDecision(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="unattended-launch-gate-panel">
      <LemonCard
        title="Unattended launch gate"
        className="unattended-launch-gate-panel"
      >
        <p className="text-sm opacity-80" data-testid="unattended-launch-gate-blurb">
          Evaluate whether an unattended Midnight Oil job is dispatch-ready.
          This never authorizes live spend — consent claim + worker remain
          separate.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Duration (minutes)</span>
            <LemonInput
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              data-testid="ulg-duration"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goals (one per line)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="ulg-goals"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved ceiling (cents)</span>
            <LemonInput
              value={approved}
              onChange={(e) => setApproved(e.target.value)}
              data-testid="ulg-ceiling"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Consent receipt id (required if ceiling &gt; 0)</span>
            <LemonInput
              value={receipt}
              onChange={(e) => setReceipt(e.target.value)}
              data-testid="ulg-receipt"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={operatorApproved}
              onChange={(e) => setOperatorApproved(e.target.checked)}
              data-testid="ulg-approved"
              disabled={busy}
            />
            Operator approved
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onEvaluate()}
            data-testid="ulg-evaluate"
          >
            {busy ? "Evaluating…" : "Evaluate launch gate"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="ulg-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="ulg-result" className="text-sm flex flex-col gap-1">
              <div data-testid="ulg-summary">
                {formatLaunchGateSummary(result)}
              </div>
              <div data-testid="ulg-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="ulg-dispatch">
                dispatch_ready={String(result.dispatch_ready)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
