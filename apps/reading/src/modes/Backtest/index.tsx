import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorBanner } from "../../components/lemon/ErrorBanner";
import LemonCard from "../../components/lemon/LemonCard";
import { ModePage } from "../../components/lemon/ModePage";
import { apiFetch } from "../../lib/api";

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
    <ModePage
      width="lg"
      header={
        <header className="space-y-2">
          <h1 className="text-2xl font-serif text-ink dark:text-bright">
            Backtest report
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
            How has the substrate changed under this synthesis since
            it landed? Per master-spec §13.8 — replay first, then
            grade outcomes against the current substrate.
          </p>
          <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
            synthesis_id = {synthesisId ?? "—"}
          </p>
        </header>
      }
    >
      {loading && (
        <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
      )}

      {error && (
        <ErrorBanner>
          {error}
        </ErrorBanner>
      )}

      {report && (
        <>
          {/* S10 row 10.11: synthesis + metric sections use LemonCard. */}
          <LemonCard
            elevation="z2"
            title="Synthesis"
          >
            <div className="p-5 space-y-2">
              <p className="text-sm text-ink dark:text-bright">
                {report.target_question}
              </p>
              <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                {report.synthesis_timestamp} · status={report.status}
                {report.implicit_recommendation
                  ? ` · ${report.implicit_recommendation}`
                  : ""}
              </p>
            </div>
          </LemonCard>

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

          <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
            <Link
              to={`/outcomes/${encodeURIComponent(report.synthesis_id)}`}
              className="text-ink dark:text-bright hover:underline"
            >
              Open outcomes grading view →
            </Link>
          </p>
        </>
      )}
    </ModePage>
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
    <LemonCard
      elevation="z1"
      className={highlight ? "bg-sun/10 dark:bg-sun/5" : ""}
    >
      <p
        className={`text-2xl font-serif ${
          highlight ? "text-sun-deep dark:text-sun" : "text-ink dark:text-bright"
        }`}
      >
        {value}
      </p>
      <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight uppercase">
        {label}
      </p>
    </LemonCard>
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
    // S10 row 10.11: Backtest data sections use LemonCard.
    <LemonCard
      elevation="z1"
      title={
        <span className="flex items-baseline justify-between gap-3">
          <span>{title}</span>
          <span className="font-sans normal-case tracking-normal text-xxs text-shadow-1 dark:text-moonlight">
            {rows.length}
          </span>
        </span>
      }
    >
      <div className="p-4 space-y-2">
        <p className="text-xs text-ink-soft dark:text-starlight">{description}</p>
        {rows.length === 0 ? (
          <p className="text-xs italic text-shadow-1 dark:text-moonlight">None.</p>
        ) : (
          <ul className="space-y-1 text-xs font-mono text-ink dark:text-bright">
            {rows.slice(0, 50).map((r, i) => (
              <li
                key={i}
                className="truncate border-b border-rule dark:border-charcoal-1 py-1"
              >
                {JSON.stringify(r)}
              </li>
            ))}
            {rows.length > 50 && (
              <li className="text-xs italic text-shadow-1 dark:text-moonlight">
                … and {rows.length - 50} more not shown
              </li>
            )}
          </ul>
        )}
      </div>
    </LemonCard>
  );
}
