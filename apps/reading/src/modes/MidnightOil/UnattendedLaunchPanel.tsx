/**
 * UnattendedLaunchPanel — Midnight Oil time + goals + ceiling brief UI.
 *
 * Free-file under MidnightOil/. Does not dispatch workers, debit budget, or
 * claim live spend (live_execution_authorized always false for this surface).
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatUnattendedSummary,
  parseUnattendedBriefResult,
  postUnattendedBrief,
  type UnattendedBriefResult,
} from "../../api/unattendedLaunch";

export interface UnattendedLaunchPanelProps {
  briefFn?: (
    req: Parameters<typeof postUnattendedBrief>[0],
  ) => Promise<UnattendedBriefResult | unknown>;
  initialDurationMinutes?: number;
  initialGoals?: string;
  initialApprovedCeilingCents?: number;
  initialRecommendedCeilingCents?: number | null;
}

export default function UnattendedLaunchPanel({
  briefFn = postUnattendedBrief,
  initialDurationMinutes = 60,
  initialGoals = "",
  initialApprovedCeilingCents = 0,
  initialRecommendedCeilingCents = null,
}: UnattendedLaunchPanelProps) {
  const [duration, setDuration] = useState(String(initialDurationMinutes));
  const [goalsRaw, setGoalsRaw] = useState(initialGoals);
  const [approved, setApproved] = useState(String(initialApprovedCeilingCents));
  const [recommended, setRecommended] = useState(
    initialRecommendedCeilingCents == null
      ? ""
      : String(initialRecommendedCeilingCents),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UnattendedBriefResult | null>(null);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const goals = goalsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const recRaw = recommended.trim();
      const raw = await briefFn({
        duration_minutes: Number(duration),
        goals,
        approved_ceiling_cents: Number(approved),
        recommended_ceiling_cents: recRaw === "" ? null : Number(recRaw),
      });
      setResult(parseUnattendedBriefResult(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="unattended-launch-panel">
      <LemonCard title="Unattended Midnight Oil brief" className="unattended-launch-panel">
        <p className="text-sm opacity-80" data-testid="unattended-launch-blurb">
          Set work duration, goals, and an approved price ceiling. This panel
          records an operator brief only — it does not start live spend or
          provider calls. Approve a recommended ceiling separately when shown.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Duration (minutes)</span>
            <LemonInput
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              data-testid="unattended-duration"
              aria-label="Duration minutes"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goals (one per line)</span>
            <textarea
              className="min-h-[80px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="unattended-goals"
              aria-label="Goals"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved ceiling (cents)</span>
            <LemonInput
              value={approved}
              onChange={(e) => setApproved(e.target.value)}
              data-testid="unattended-approved"
              aria-label="Approved ceiling cents"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Recommended ceiling (cents, optional)</span>
            <LemonInput
              value={recommended}
              onChange={(e) => setRecommended(e.target.value)}
              data-testid="unattended-recommended"
              aria-label="Recommended ceiling cents"
              disabled={busy}
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onSubmit()}
            data-testid="unattended-submit"
          >
            {busy ? "Validating…" : "Validate unattended brief"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="unattended-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="unattended-result" className="flex flex-col gap-1 text-sm">
              <div data-testid="unattended-summary">
                {formatUnattendedSummary(result)}
              </div>
              <div data-testid="unattended-live">
                live_execution_authorized={String(result.live_execution_authorized)}
              </div>
              <div data-testid="unattended-authority">
                authority={result.authority}
              </div>
              <ul className="text-xs list-disc pl-4" data-testid="unattended-notes">
                {result.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
