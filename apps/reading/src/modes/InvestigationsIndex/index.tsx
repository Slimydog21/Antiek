import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import { requireInvestigationId } from "../../lib/investigationData";

/**
 * Investigations index — operator-facing list of past + in-flight
 * investigations (master-spec §4.1).
 *
 * Reads ``GET /investigations`` and renders each row with status,
 * cost, and quick-links to the workstation and the trajectory
 * replay surface. Filterable by status. Operators arrive here from
 * the command palette or by clicking 'Investigations' in the header.
 */

interface InvestigationRow {
  investigation_id: string;
  question: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  cost_usd_total: number;
  parent_investigation_id: string | null;
}

const STATUS_FILTERS = ["all", "in_progress", "completed", "failed"] as const;

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

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function validationDetail(value: unknown): string {
  const body = record(value);
  const detail = body?.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  const nested = record(detail);
  return nonEmptyString(nested?.message) ?? "rejected";
}

function safeInvestigationRow(value: unknown): InvestigationRow | null {
  const row = record(value);
  const investigationId = nonEmptyString(row?.investigation_id);
  if (!row || !investigationId) return null;
  return {
    investigation_id: investigationId,
    question: nullableString(row.question),
    status: nonEmptyString(row.status) ?? "in_progress",
    started_at: nullableString(row.started_at),
    completed_at: nullableString(row.completed_at),
    cost_usd_total: finiteNonNegativeNumber(row.cost_usd_total) ?? 0,
    parent_investigation_id: nullableString(row.parent_investigation_id),
  };
}

function safeInvestigationRows(value: unknown): InvestigationRow[] {
  const body = record(value);
  const rows = Array.isArray(body?.investigations) ? body.investigations : [];
  return rows.flatMap((item) => {
    const row = safeInvestigationRow(item);
    return row ? [row] : [];
  });
}

function clampMaxSubQuestions(value: unknown): number {
  return typeof value === "number" && Number.isSafeInteger(value)
    ? Math.max(1, Math.min(20, value))
    : 1;
}

export default function InvestigationsIndex() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<InvestigationRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  // "Start new investigation" form draft.
  const [draftQuestion, setDraftQuestion] = useState<string>("");
  const [draftContext, setDraftContext] = useState<string>("");
  const [draftTopic, setDraftTopic] = useState<string>("");
  const [draftMaxSubQs, setDraftMaxSubQs] = useState<number>(8);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const startInvestigation = async () => {
    if (submitting || draftQuestion.trim().length < 3) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await apiFetch("/investigations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: draftQuestion.trim(),
          context: draftContext.trim(),
          topic_slug: draftTopic.trim() || null,
          max_sub_questions: draftMaxSubQs,
        }),
      });
      if (resp.status === 422) {
        const body: unknown = await resp.json().catch(() => null);
        throw new Error(
          `Validation: ${validationDetail(body)}`,
        );
      }
      if (!resp.ok) {
        throw new Error(`POST /investigations: HTTP ${resp.status}`);
      }
      const created = record(await resp.json());
      const newId = requireInvestigationId(created?.investigation_id);
      // Reset draft, then navigate into the new investigation's
      // workstation. Listing refreshes in the background.
      setDraftQuestion("");
      setDraftContext("");
      setDraftTopic("");
      setDraftMaxSubQs(8);
      navigate(`/inv/${encodeURIComponent(newId)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filter !== "all") params.set("status", filter);
      const resp = await apiFetch(`/investigations?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /investigations: HTTP ${resp.status}`);
      }
      setRows(safeInvestigationRows(await resp.json()));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totalCost = useMemo(
    () => rows.reduce((acc, r) => acc + (finiteNonNegativeNumber(r.cost_usd_total) ?? 0), 0),
    [rows],
  );

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Investigations
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              All investigations the substrate has seen, newest first.
              Click an investigation to open it in the workstation;
              click 'replay' to open its trajectory.
            </p>
          </header>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <h2 className="text-sm font-serif text-ink dark:text-bright">
              Start a new investigation
            </h2>
            <input
              type="text"
              value={draftQuestion}
              onChange={(e) => setDraftQuestion(e.target.value)}
              placeholder="What's the question? (≥ 3 chars)"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
            <textarea
              value={draftContext}
              onChange={(e) => setDraftContext(e.target.value)}
              rows={2}
              placeholder="Context (optional)"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
            />
            <div className="grid grid-cols-3 gap-2 items-end">
              <div className="space-y-1 col-span-2">
                <label
                  htmlFor="investigation-topic-slug"
                  className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight"
                >
                  Topic slug (optional)
                </label>
                <input
                  id="investigation-topic-slug"
                  type="text"
                  value={draftTopic}
                  onChange={(e) => setDraftTopic(e.target.value)}
                  placeholder="e.g. quantum_neutral_atoms_2026"
                  className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              </div>
              <div className="space-y-1">
                <label
                  htmlFor="investigation-max-sub-questions"
                  className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight"
                >
                  Max sub-questions (1-20)
                </label>
                <input
                  id="investigation-max-sub-questions"
                  type="number"
                  min={1}
                  max={20}
                  value={draftMaxSubQs}
                  onChange={(e) =>
                    setDraftMaxSubQs(clampMaxSubQuestions(Number(e.target.value)))
                  }
                  className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              </div>
            </div>
            <button
              type="button"
              onClick={() => void startInvestigation()}
              disabled={submitting || draftQuestion.trim().length < 3}
              className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
            >
              {submitting ? "Starting…" : "Start investigation"}
            </button>
          </section>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {STATUS_FILTERS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setFilter(s)}
                    className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                      filter === s
                        ? "bg-ink text-white"
                        : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                    }`}
                  >
                    {s.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
              <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                {rows.length} shown · ${totalCost.toFixed(2)} total cost
              </p>
            </div>
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
              No investigations match this filter.
            </p>
          )}

          {rows.length > 0 && (
            <section className="border border-rule dark:border-charcoal-1 rounded-md divide-y divide-rule dark:divide-charcoal-1">
              {rows.map((r) => (
                <InvestigationListRow key={r.investigation_id} row={r} />
              ))}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

function InvestigationListRow({ row: r }: { row: InvestigationRow }) {
  const costUsd = finiteNonNegativeNumber(r.cost_usd_total) ?? 0;
  return (
    <article className="px-4 py-3 hover:bg-ice-1 dark:bg-charcoal-2 transition-colors">
      <div className="flex items-baseline justify-between gap-3">
        <Link
          to={`/inv/${encodeURIComponent(r.investigation_id)}`}
          className="flex-1 min-w-0"
        >
          <p className="text-sm font-serif text-ink dark:text-bright truncate">
            {r.question ?? r.investigation_id}
          </p>
          <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
            {r.investigation_id}
            {r.parent_investigation_id ? (
              <> · parent: {r.parent_investigation_id.slice(0, 12)}</>
            ) : null}
          </p>
        </Link>
        <div className="text-right shrink-0 space-y-0.5">
          <span
            className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded ${
              r.status === "completed"
                ? "bg-emerald-100 text-emerald-700"
                : r.status === "failed"
                  ? "bg-red-50 text-emperor"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
            }`}
          >
            {r.status}
          </span>
          <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
            ${costUsd.toFixed(4)}
          </p>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        <Link
          to={`/replay/${encodeURIComponent(r.investigation_id)}`}
          className="hover:underline hover:text-ink dark:text-bright"
        >
          replay →
        </Link>
        {r.started_at && <span>started {r.started_at}</span>}
        {r.completed_at && <span>done {r.completed_at}</span>}
      </div>
    </article>
  );
}
