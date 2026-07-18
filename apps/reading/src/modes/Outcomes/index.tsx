import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";

/**
 * Outcomes surface (master-spec §13.8 + Phase 8 input).
 *
 * Operator-graded outcomes for synthesis pages. Per master-spec:
 *
 *   "Outcomes are first-class signals; without them, accept/reject
 *    verdicts on candidate skill patches degrade into vibes."
 *
 * Flow:
 *   1. Operator opens a synthesis page (via /inv/:id or Mode A).
 *   2. Decides whether thesis was validated, falsified, or remains
 *      indeterminate. Records each outcome with a one-line note.
 *   3. The compounding gate (Phase 8) reads these via
 *      ``middleware.backtest.db.load_outcomes_for_synthesis`` and
 *      decides accept/reject for candidate skill patches.
 *
 * The UI is intentionally narrow — three columns (validated /
 * falsified / indeterminate), one button per outcome — so the
 * operator can grade quickly. No dropdowns, no modal.
 */

interface OutcomeRow {
  outcome_id: string;
  observer: string;
  observed_at: string;
  thesis_outcomes: { kind: string; note: string }[];
  falsification_outcomes: { kind: string; note: string }[];
  execution_risk_outcomes: { kind: string; note: string }[];
  notes: string | null;
}

type OutcomeKind = "validated" | "falsified" | "indeterminate";

export default function Outcomes() {
  const { synthesisId } = useParams<{ synthesisId: string }>();
  const [outcomes, setOutcomes] = useState<OutcomeRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [draftNote, setDraftNote] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    if (!synthesisId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(`/outcomes/${encodeURIComponent(synthesisId)}`);
      if (!resp.ok) {
        throw new Error(`GET /outcomes failed: HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setOutcomes(data.outcomes ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [synthesisId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const submit = async (kind: OutcomeKind) => {
    if (!synthesisId || submitting) return;
    setSubmitting(true);
    try {
      const note = draftNote.trim() || `Graded ${kind}.`;
      const body = {
        synthesis_id: synthesisId,
        observer: "__operator__",
        thesis_outcomes:
          kind === "validated" ? [{ kind: "validated", note }] : [],
        falsification_outcomes:
          kind === "falsified" ? [{ kind: "falsified", note }] : [],
        execution_risk_outcomes:
          kind === "indeterminate" ? [{ kind: "indeterminate", note }] : [],
        notes: draftNote || null,
      };
      const resp = await apiFetch("/outcomes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        throw new Error(`POST /outcomes failed: HTTP ${resp.status}`);
      }
      setDraftNote("");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const counts = useMemo(() => {
    return {
      validated: outcomes.reduce(
        (n, o) => n + o.thesis_outcomes.length,
        0,
      ),
      falsified: outcomes.reduce(
        (n, o) => n + o.falsification_outcomes.length,
        0,
      ),
      indeterminate: outcomes.reduce(
        (n, o) => n + o.execution_risk_outcomes.length,
        0,
      ),
    };
  }, [outcomes]);

  // S10 row 10.13 — Outcomes/:id wraps the grading surface in
  // PanelHost. The spec called for "left = sources, right = trace"
  // but the page's actual data is a single-form grading view —
  // there's no separate sources or trace dataset available here.
  // We wrap with NO starters so the operator can open ProjectTree
  // / AISidecar / etc. via shortcuts but the main grading flow
  // stays a single column. A future cycle that surfaces backtest
  // sources + replay trace inline can add the corresponding
  // PanelKinds + starters.
  return (
    <PanelHost>
      <main className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-8">
          <SessionBrandChrome testIdPrefix="outcomes-detail" title="Outcomes">
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Grade the synthesis page below. Outcomes feed the
              Phase 8 skill-growth gate (compounding/skill_growth/gate.py).
              Per master-spec §13.8: &lsquo;without operator-graded outcomes,
              accept/reject verdicts on candidate skill patches degrade
              into vibes.&rsquo;
            </p>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight flex items-center gap-2 flex-wrap">
              <span>synthesis_id = {synthesisId ?? "—"}</span>
              {synthesisId && (
                <Link
                  to={`/backtest/${encodeURIComponent(synthesisId)}`}
                  className="text-ink dark:text-bright hover:underline"
                >
                  open backtest report →
                </Link>
              )}
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-4">
            <h2 className="text-base font-serif text-ink dark:text-bright">Grade now</h2>
            <textarea
              value={draftNote}
              onChange={(e) => setDraftNote(e.target.value)}
              placeholder="One-line rationale (optional but useful for future review)"
              className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
              rows={2}
              disabled={submitting}
            />
            <div className="grid grid-cols-3 gap-2">
              <GradeButton
                label="Validated"
                onClick={() => submit("validated")}
                disabled={submitting}
                accent="bg-emerald-700 hover:bg-emerald-600"
              />
              <GradeButton
                label="Falsified"
                onClick={() => submit("falsified")}
                disabled={submitting}
                accent="bg-rose-700 hover:bg-rose-600"
              />
              <GradeButton
                label="Indeterminate"
                onClick={() => submit("indeterminate")}
                disabled={submitting}
                accent="bg-shadow-2 hover:bg-shadow-1"
              />
            </div>
          </section>

          <section className="grid grid-cols-3 gap-4">
            <CountCard label="Validated" count={counts.validated} accent="text-emerald-700" />
            <CountCard label="Falsified" count={counts.falsified} accent="text-rose-700" />
            <CountCard label="Indeterminate" count={counts.indeterminate} accent="text-ink dark:text-bright" />
          </section>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
            <h2 className="text-base font-serif text-ink dark:text-bright">History</h2>
            {loading ? (
              <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
            ) : outcomes.length === 0 ? (
              <p className="text-sm text-shadow-1 dark:text-moonlight italic">
                No outcomes recorded yet for this synthesis.
              </p>
            ) : (
              <ul className="divide-y divide-rule dark:divide-charcoal-1">
                {outcomes.map((o) => (
                  <li key={o.outcome_id} className="py-2 space-y-1">
                    <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                      {o.observed_at} · {o.observer}
                    </p>
                    {o.thesis_outcomes.map((t, i) => (
                      <p key={`t-${i}`} className="text-sm text-emerald-700">
                        validated — {t.note}
                      </p>
                    ))}
                    {o.falsification_outcomes.map((f, i) => (
                      <p key={`f-${i}`} className="text-sm text-rose-700">
                        falsified — {f.note}
                      </p>
                    ))}
                    {o.execution_risk_outcomes.map((e, i) => (
                      <p key={`e-${i}`} className="text-sm text-ink dark:text-bright">
                        indeterminate — {e.note}
                      </p>
                    ))}
                    {o.notes && (
                      <p className="text-xs text-shadow-1 dark:text-moonlight italic">
                        Note: {o.notes}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </main>
    </PanelHost>
  );
}

function GradeButton({
  label,
  onClick,
  disabled,
  accent,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  accent: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-2 rounded-md text-white text-sm font-medium transition-colors disabled:opacity-50 ${accent}`}
    >
      {label}
    </button>
  );
}

function CountCard({
  label,
  count,
  accent,
}: { label: string; count: number; accent: string }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-4 py-3 text-center">
      <p className={`text-2xl font-serif ${accent}`}>{count}</p>
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight uppercase">{label}</p>
    </div>
  );
}
