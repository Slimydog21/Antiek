import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonTable from "../../components/lemon/LemonTable";
import { apiFetch } from "../../lib/api";

/**
 * Operator-facing outcomes audit surface (master-spec §13.8).
 *
 * Reads ``GET /outcomes`` for the cross-investigation grading
 * history; each row links to ``/outcomes/:synthesisId`` where the
 * full grade-history + grade-now interface lives.
 *
 * Per master-spec §13.8: 'without operator-graded outcomes,
 * accept/reject verdicts on candidate skill patches degrade into
 * vibes.' This index surfaces the substrate's record of what the
 * operator has actually weighed in on.
 */

interface OutcomeRow {
  outcome_id: string;
  synthesis_id: string;
  observer: string;
  observed_at: string;
}

function observerLabel(observer: string): string {
  if (observer === "__operator__") return "You";
  return observer || "Reviewer";
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function safeOutcomeRow(value: unknown): OutcomeRow | null {
  const row = record(value);
  const outcomeId = nonEmptyString(row?.outcome_id);
  const synthesisId = nonEmptyString(row?.synthesis_id);
  if (!row || !outcomeId || !synthesisId) return null;
  return {
    outcome_id: outcomeId,
    synthesis_id: synthesisId,
    observer: nonEmptyString(row.observer) ?? "",
    observed_at: nonEmptyString(row.observed_at) ?? "",
  };
}

function safeOutcomeRows(value: unknown): OutcomeRow[] {
  const body = record(value);
  const outcomes = Array.isArray(body?.outcomes) ? body.outcomes : [];
  const seen = new Set<string>();
  return outcomes.flatMap((item) => {
    const row = safeOutcomeRow(item);
    if (!row || seen.has(row.outcome_id)) return [];
    seen.add(row.outcome_id);
    return [row];
  });
}

function observerFilterParam(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.toLowerCase() === "you" ? "__operator__" : trimmed;
}

function reviewTitle(row: OutcomeRow, index: number): string {
  return `Review ${index + 1} from ${row.observed_at || "an earlier session"}`;
}

export default function OutcomesIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<OutcomeRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [observerFilter, setObserverFilter] = useState<string>("");
  const loadSeq = useRef(0);

  const reload = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (observerFilter.trim()) {
        params.set("observer", observerFilterParam(observerFilter));
      }
      params.set("limit", "200");
      const resp = await apiFetch(`/outcomes?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`Could not load review history (HTTP ${resp.status}).`);
      }
      const nextRows = safeOutcomeRows(await resp.json());
      if (loadSeq.current === seq) {
        setRows(nextRows);
      }
    } catch (e: unknown) {
      if (loadSeq.current === seq) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (loadSeq.current === seq) {
        setLoading(false);
      }
    }
  }, [observerFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Outcomes audit
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Review history across your research. Open any row to see the
              graded answer, the replay, and the notes behind the decision.
            </p>
          </header>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4">
            <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight block mb-1">
              Filter by reviewer
            </label>
            <input
              type="text"
              value={observerFilter}
              onChange={(e) => setObserverFilter(e.target.value)}
              aria-label="Filter by reviewer"
              placeholder="Type “you” or an exact reviewer handle"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && rows.length === 0 && !error && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              {observerFilter.trim()
                ? "No reviews match this filter yet."
                : "No reviews yet."}{" "}
              Once you grade an answer as validated, falsified, or
              indeterminate, it appears here with a link back to the full
              review.
            </p>
          )}

          {rows.length > 0 && (
            // S10 acceptance: OutcomesIndex uses LemonTable.
            <LemonTable
              rows={rows}
              rowKey={(r) => r.outcome_id}
              onRowClick={(r) =>
                navigate(`/outcomes/${encodeURIComponent(r.synthesis_id)}`)
              }
              columns={[
                {
                  key: "synthesis",
                  header: "Review",
                  width: "55%",
                  render: (r, i) => (
                    <div>
                      <p className="font-serif text-ink dark:text-bright truncate">
                        {reviewTitle(r, i)}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        Open the graded answer and replay
                      </p>
                    </div>
                  ),
                },
                {
                  key: "observed",
                  header: "Reviewed by",
                  render: (r) => (
                    <span className="font-serif text-[12px] text-ink-soft dark:text-starlight">
                      {observerLabel(r.observer)}
                    </span>
                  ),
                },
                {
                  key: "outcome",
                  header: "Action",
                  align: "right",
                  render: () => (
                    <span className="font-serif text-[12px] text-ink-soft dark:text-starlight">
                      Open details
                    </span>
                  ),
                },
              ]}
            />
          )}
        </div>
      </main>
    </div>
  );
}
