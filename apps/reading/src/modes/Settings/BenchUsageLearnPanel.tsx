/**
 * BenchUsageLearnPanel — recursive next-week weight proposals from usage.
 *
 * Consumes POST /settings/antiek-bench/usage-learn (PR #804). Advisory only.
 * Does not own Settings/index.tsx or substrate/antiek_bench.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatAuthority,
  formatWeight,
  parseUsageLearnProposal,
  postUsageLearn,
  type UsageLearnProposal,
} from "../../api/benchUsageLearn";

export interface BenchUsageLearnPanelProps {
  /**
   * Injectable propose. Return value is re-validated so non-advisory
   * authority cannot render as a successful proposal.
   */
  proposeFn?: (
    req: Parameters<typeof postUsageLearn>[0],
  ) => Promise<UsageLearnProposal | unknown>;
  initialWeekId?: string;
  initialEventsJson?: string;
}

const DEFAULT_EVENTS = `[
  {"task":"deep_research","success":false,"model_id":"m1"},
  {"task":"deep_research","success":true,"model_id":"m1"},
  {"task":"general","success":true,"model_id":"m2"}
]`;

export default function BenchUsageLearnPanel({
  proposeFn = postUsageLearn,
  initialWeekId = "",
  initialEventsJson = DEFAULT_EVENTS,
}: BenchUsageLearnPanelProps) {
  const [weekId, setWeekId] = useState(initialWeekId);
  const [eventsJson, setEventsJson] = useState(initialEventsJson);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UsageLearnProposal | null>(null);

  async function onPropose() {
    setBusy(true);
    setError(null);
    try {
      let usage_events: Array<{
        task?: string;
        success?: boolean | null;
        model_id?: string;
        notes?: string;
      }> = [];
      const raw = eventsJson.trim();
      if (raw) {
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) {
          throw new Error("usage_events JSON must be an array");
        }
        usage_events = parsed as typeof usage_events;
      }
      const rawResult = await proposeFn({
        week_id: weekId,
        usage_events,
      });
      setResult(parseUsageLearnProposal(rawResult));
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="bench-usage-learn-panel">
      <LemonCard title="Antiek-bench usage learn" className="bench-usage-learn-panel">
        <p className="text-sm opacity-80" data-testid="bench-usage-learn-blurb">
          Propose next-week sub-benchmark weights from injected usage outcomes
          (what worked / what failed). Advisory only — never production bench
          mutation authority.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Week id (optional)</span>
            <LemonInput
              value={weekId}
              onChange={(e) => setWeekId(e.target.value)}
              placeholder="2026-W28"
              data-testid="bench-usage-learn-week"
              aria-label="Week id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Usage events JSON array</span>
            <textarea
              className="min-h-[120px] w-full rounded border border-border bg-bg-light px-2 py-1 font-mono text-xs"
              value={eventsJson}
              onChange={(e) => setEventsJson(e.target.value)}
              data-testid="bench-usage-learn-events"
              aria-label="Usage events JSON"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onPropose()}
            data-testid="bench-usage-learn-propose"
          >
            {busy ? "Proposing…" : "Propose next-week weights"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="bench-usage-learn-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="bench-usage-learn-result" className="flex flex-col gap-2">
              <div data-testid="bench-usage-learn-authority">
                Authority: {formatAuthority(result.authority)}
              </div>
              <div data-testid="bench-usage-learn-week-echo">
                Week: {result.week_id || "(none)"}
              </div>
              <div data-testid="bench-usage-learn-incomplete">
                Incomplete: {result.incomplete ? "yes" : "no"}
              </div>
              <ul data-testid="bench-usage-learn-weights">
                {result.task_weights.length === 0 ? (
                  <li data-testid="bench-usage-learn-empty">no task weights</li>
                ) : (
                  result.task_weights.map((w) => (
                    <li
                      key={w.task}
                      data-testid={`bench-usage-learn-weight-${w.task}`}
                    >
                      {w.task}: {formatWeight(w.weight)} (ok={w.n_success} fail=
                      {w.n_failure}) — {w.rationale}
                    </li>
                  ))
                )}
              </ul>
              {result.notes.length > 0 ? (
                <ul data-testid="bench-usage-learn-notes">
                  {result.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
