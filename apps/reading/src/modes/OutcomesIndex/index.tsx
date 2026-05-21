import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

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

export default function OutcomesIndex() {
  const [rows, setRows] = useState<OutcomeRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [observerFilter, setObserverFilter] = useState<string>("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (observerFilter.trim()) {
        params.set("observer", observerFilter.trim());
      }
      params.set("limit", "200");
      const resp = await apiFetch(`/outcomes?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /outcomes failed: HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setRows(data.outcomes ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [observerFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-white">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-stone-900">
              Outcomes audit
            </h1>
            <p className="text-sm text-stone-600 leading-relaxed">
              Cross-investigation grading history. Per master-spec
              §13.8: outcomes are first-class signals that feed the
              Phase 8 skill-growth gate — replay first, grade second.
            </p>
          </header>

          <section className="border border-stone-200 rounded-md p-4">
            <label className="text-[10px] font-mono uppercase text-stone-500 block mb-1">
              Filter by observer
            </label>
            <input
              type="text"
              value={observerFilter}
              onChange={(e) => setObserverFilter(e.target.value)}
              placeholder="__operator__ — leave blank for all"
              className="w-full text-xs font-mono text-stone-900 border border-stone-200 rounded p-2"
            />
          </section>

          {error && (
            <p className="text-sm text-red-700 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-stone-500 italic">Loading…</p>
          )}

          {!loading && rows.length === 0 && !error && (
            <p className="text-sm text-stone-500 italic">
              No outcomes recorded yet for this filter. Grade a
              synthesis at /outcomes/&lt;synthesis_id&gt; to populate
              this view.
            </p>
          )}

          {rows.length > 0 && (
            <section className="border border-stone-200 rounded-md divide-y divide-stone-100">
              {rows.map((r) => (
                <Link
                  key={r.outcome_id}
                  to={`/outcomes/${encodeURIComponent(r.synthesis_id)}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-stone-50 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-mono text-stone-900 truncate">
                      {r.synthesis_id}
                    </p>
                    <p className="text-[11px] font-mono text-stone-500">
                      {r.observed_at} · {r.observer}
                    </p>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider font-mono text-stone-400 shrink-0">
                    {r.outcome_id.slice(0, 12)}
                  </span>
                </Link>
              ))}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
