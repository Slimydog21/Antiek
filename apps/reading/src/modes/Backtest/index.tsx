import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

/**
 * Backtest report UI (master-spec §13.8).
 *
 * Reads ``GET /backtest/:synthesisId`` and renders the report. The
 * substrate's middleware/backtest/analysis.py composes the report
 * from substrate state; this surface displays it for the operator
 * before they grade outcomes.
 */

interface BacktestReport {
  synthesis_id: string;
  synthesis_timestamp: string;
  target_question: string;
  status: string;
  implicit_recommendation: string | null;
  substrate_manifest_counts: Record<string, number>;
  added_edges_since: number;
  superseded_edges_since: number;
  cited_edges_now_superseded_count: number;
  chunks_retired_downward_count: number;
  outcomes_recorded: number;
  cited_edges_now_superseded: Record<string, unknown>[];
  chunks_retired_downward: Record<string, unknown>[];
  outcomes: Record<string, unknown>[];
}

export default function Backtest() {
  const { synthesisId } = useParams<{ synthesisId: string }>();
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!synthesisId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `/backtest/${encodeURIComponent(synthesisId)}`,
      );
      if (resp.status === 404) {
        setReport(null);
        setError("No backtest available — synthesis not archived.");
        return;
      }
      if (!resp.ok) {
        throw new Error(`GET /backtest: HTTP ${resp.status}`);
      }
      setReport(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [synthesisId]);

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
              Backtest report
            </h1>
            <p className="text-sm text-stone-600 leading-relaxed">
              How has the substrate changed under this synthesis since
              it landed? Per master-spec §13.8 — replay first, then
              grade outcomes against the current substrate.
            </p>
            <p className="text-xs font-mono text-stone-500">
              synthesis_id = {synthesisId ?? "—"}
            </p>
          </header>

          {loading && (
            <p className="text-sm text-stone-500 italic">Loading…</p>
          )}

          {error && (
            <p className="text-sm text-red-700 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {report && (
            <>
              <section className="border border-stone-200 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-stone-900">
                  Synthesis
                </h2>
                <p className="text-sm text-stone-900">
                  {report.target_question}
                </p>
                <p className="text-[11px] font-mono text-stone-500">
                  {report.synthesis_timestamp} · status={report.status}
                  {report.implicit_recommendation
                    ? ` · ${report.implicit_recommendation}`
                    : ""}
                </p>
              </section>

              <section className="grid grid-cols-3 gap-3">
                <Metric
                  label="Edges added since"
                  value={report.added_edges_since}
                />
                <Metric
                  label="Edges superseded since"
                  value={report.superseded_edges_since}
                />
                <Metric
                  label="Load-bearing edges invalidated"
                  value={report.cited_edges_now_superseded_count}
                  highlight={report.cited_edges_now_superseded_count > 0}
                />
                <Metric
                  label="Cited chunks demoted"
                  value={report.chunks_retired_downward_count}
                  highlight={report.chunks_retired_downward_count > 0}
                />
                <Metric
                  label="Outcomes recorded"
                  value={report.outcomes_recorded}
                />
                <Metric
                  label="Substrate manifest entries"
                  value={Object.values(report.substrate_manifest_counts).reduce(
                    (a, b) => a + b,
                    0,
                  )}
                />
              </section>

              <DetailList
                title="Load-bearing edges now superseded"
                description="Cited at synthesis time but later marked superseded — the conclusion may need revisiting."
                rows={report.cited_edges_now_superseded}
              />
              <DetailList
                title="Cited chunks retired downward in tier"
                description="Chunks the synthesis cited but the substrate later demoted (e.g., from Tier 1 to Tier 3)."
                rows={report.chunks_retired_downward}
              />
              <DetailList
                title="Outcomes recorded against this synthesis"
                description="Operator-graded verdicts. Replay then grade — outcomes feed the Phase 8 gate."
                rows={report.outcomes}
              />

              <p className="text-xs font-mono text-stone-500">
                <Link
                  to={`/outcomes/${encodeURIComponent(report.synthesis_id)}`}
                  className="text-stone-700 hover:underline"
                >
                  Open outcomes grading view →
                </Link>
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function Metric({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`border rounded-md px-3 py-2 ${
        highlight ? "border-amber-300 bg-amber-50" : "border-stone-200"
      }`}
    >
      <p
        className={`text-2xl font-serif ${
          highlight ? "text-amber-800" : "text-stone-900"
        }`}
      >
        {value}
      </p>
      <p className="text-[10px] font-mono text-stone-500 uppercase">
        {label}
      </p>
    </div>
  );
}

function DetailList({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: Record<string, unknown>[];
}) {
  return (
    <section className="border border-stone-200 rounded-md p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-stone-900">{title}</h3>
        <span className="text-[10px] uppercase font-mono text-stone-500">
          {rows.length}
        </span>
      </div>
      <p className="text-xs text-stone-600">{description}</p>
      {rows.length === 0 ? (
        <p className="text-xs italic text-stone-500">None.</p>
      ) : (
        <ul className="space-y-1 text-[11px] font-mono text-stone-700">
          {rows.slice(0, 50).map((r, i) => (
            <li
              key={i}
              className="truncate border-b border-stone-100 py-1"
            >
              {JSON.stringify(r)}
            </li>
          ))}
          {rows.length > 50 && (
            <li className="text-xs italic text-stone-500">
              … and {rows.length - 50} more not shown
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
