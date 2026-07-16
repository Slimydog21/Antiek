import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
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

export default function OutcomesIndex() {
  const navigate = useNavigate();
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
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              {/* Session thinking mark — densify Outcomes door with living-TV
                  brand chrome so the audit surface consumes session Imagine
                  assets, not inventory-only. */}
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="outcomes-home-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Outcomes audit
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="outcomes-home-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Cross-investigation grading history. Per master-spec
              §13.8: outcomes are first-class signals that feed the
              Phase 8 skill-growth gate — replay first, grade second.
            </p>
          </header>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4">
            <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight block mb-1">
              Filter by observer
            </label>
            <input
              type="text"
              value={observerFilter}
              onChange={(e) => setObserverFilter(e.target.value)}
              placeholder="__operator__ — leave blank for all"
              className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
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
            // SPR-06 M3 — the empty state explains what Outcomes IS (the
            // cross-investigation grading / quality history of your
            // investigations), so a first-time user isn't confused by a blank
            // tab. Reuses the SHIPPED outcomes data (GET /outcomes →
            // middleware.backtest.db.load_outcomes_for_synthesis, read by the
            // Phase 8 gate); no new grading concept/table/rubric is introduced.
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              This is the grading / quality history of your
              investigations — each row is a synthesis you graded
              validated, falsified, or indeterminate, kept as the
              cross-investigation record the Phase 8 gate reads. Nothing
              graded yet for this filter; grade a synthesis at
              /outcomes/&lt;synthesis_id&gt; and it appears here.
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
                  header: "Synthesis",
                  width: "55%",
                  render: (r) => (
                    <span className="font-mono text-ink dark:text-bright truncate inline-block max-w-full">
                      {r.synthesis_id}
                    </span>
                  ),
                },
                {
                  key: "observed",
                  header: "Observed",
                  render: (r) => (
                    <span className="font-mono text-[12px] text-ink-soft dark:text-starlight">
                      {r.observed_at} · {r.observer}
                    </span>
                  ),
                },
                {
                  key: "outcome",
                  header: "Outcome id",
                  align: "right",
                  render: (r) => (
                    <span className="font-mono text-[11px] text-ink-mute dark:text-moonlight">
                      {r.outcome_id.slice(0, 12)}
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
