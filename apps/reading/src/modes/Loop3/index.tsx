import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Loop 3 unlock checklist (master-spec §14.2 + §13.7).
 *
 * Operator-facing surface for the 5 RL-training unlock criteria.
 * Reads /loop-3/status, writes via /loop-3/checklist. Per the
 * master spec: criteria-met ≠ training-authorized — the env-var
 * flip (ANTIEK_LOOP3_UNLOCKED=1) is the operator's separate, final
 * action. Both gates must hold for fully_unlocked == True.
 */

interface Loop3Status {
  criteria: Record<string, boolean>;
  notes: Record<string, string>;
  all_criteria_met: boolean;
  env_unlocked: boolean;
  fully_unlocked: boolean;
}

const CRITERIA_ORDER = [
  "trajectory_volume",
  "sft_readiness",
  "validated_reward",
  "open_weight_justification",
  "eval_headroom",
] as const;

const CRITERIA_DESCRIPTIONS: Record<string, string> = {
  trajectory_volume:
    "Sufficient real trajectory volume harvested to train at scale " +
    "without degenerating to overfit. Operator-defined threshold.",
  sft_readiness:
    "SFT data quality + format ready: trajectories carry the right " +
    "(observation, action, ground-truth-action) triples per role.",
  validated_reward:
    "Rubric verifier calibrated against operator's manual review — " +
    "no systematic skew at the scale the env will train at.",
  open_weight_justification:
    "Written justification for going open-weight vs API: cost, " +
    "control, latency, IP defensibility. Operator on record.",
  eval_headroom:
    "Eval suite has measurable headroom: baseline score < 0.9 on " +
    "the held-out set, so RL has somewhere to climb.",
};

export default function Loop3() {
  const [status, setStatus] = useState<Loop3Status | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingNotes, setPendingNotes] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/loop-3/status");
      if (!resp.ok) {
        throw new Error(`GET /loop-3/status failed: HTTP ${resp.status}`);
      }
      setStatus(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const flipCriterion = async (criterion: string, met: boolean) => {
    setSubmitting(criterion);
    try {
      const note = (pendingNotes[criterion] ?? status?.notes[criterion] ?? "").trim();
      const resp = await apiFetch("/loop-3/checklist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ criterion, met, note }),
      });
      if (!resp.ok) {
        throw new Error(`POST /loop-3/checklist failed: HTTP ${resp.status}`);
      }
      setPendingNotes((prev) => {
        const next = { ...prev };
        delete next[criterion];
        return next;
      });
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-8">
          <SessionBrandChrome
            testIdPrefix="loop3-home"
            title="Loop 3 unlock checklist"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              The five criteria from{" "}
              <code>docs/loop_3_unlock_criteria.md</code>. Per master-spec
              §14.2: criteria-met is NOT the same decision as training-
              authorized. Even with all five flipped, the operator must
              also set <code>ANTIEK_LOOP3_UNLOCKED=1</code> in the env
              for substrate-level training-time work to run.
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {status && (
            <>
              <section className="grid grid-cols-3 gap-3">
                <Tile
                  label="All criteria met"
                  value={status.all_criteria_met}
                />
                <Tile label="Env unlocked" value={status.env_unlocked} />
                <Tile
                  label="Fully unlocked"
                  value={status.fully_unlocked}
                  highlight={status.fully_unlocked}
                />
              </section>

              <section className="space-y-3">
                {CRITERIA_ORDER.map((c) => {
                  const met = status.criteria[c] ?? false;
                  const note = pendingNotes[c] ?? status.notes[c] ?? "";
                  return (
                    <div
                      key={c}
                      className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2"
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-sm font-mono text-ink dark:text-bright">
                          {c}
                        </h3>
                        <span
                          className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded ${
                            met
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
                          }`}
                        >
                          {met ? "MET" : "NOT MET"}
                        </span>
                      </div>
                      <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
                        {CRITERIA_DESCRIPTIONS[c]}
                      </p>
                      <textarea
                        value={note}
                        onChange={(e) =>
                          setPendingNotes((prev) => ({
                            ...prev,
                            [c]: e.target.value,
                          }))
                        }
                        rows={2}
                        placeholder="Audit note — what evidence is this criterion based on?"
                        className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
                      />
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void flipCriterion(c, !met)}
                          disabled={submitting === c}
                          className={`px-3 py-1 rounded-md text-white text-xs font-medium transition-colors disabled:opacity-50 ${
                            met
                              ? "bg-shadow-2 hover:bg-shadow-1"
                              : "bg-emerald-700 hover:bg-emerald-600"
                          }`}
                        >
                          {met ? "Mark not met" : "Mark met"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </section>
            </>
          )}

          {loading && !status && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}
        </div>
      </main>
    </div>
  );
}

function Tile({
  label,
  value,
  highlight,
}: { label: string; value: boolean; highlight?: boolean }) {
  return (
    <div
      className={`border rounded-md px-4 py-3 text-center ${
        highlight
          ? "border-emerald-500 bg-emerald-50"
          : "border-rule dark:border-charcoal-1"
      }`}
    >
      <p
        className={`text-base font-serif ${
          value ? "text-emerald-700" : "text-shadow-1 dark:text-moonlight"
        }`}
      >
        {value ? "YES" : "NO"}
      </p>
      <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">{label}</p>
    </div>
  );
}
