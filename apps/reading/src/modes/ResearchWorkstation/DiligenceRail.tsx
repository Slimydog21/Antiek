/**
 * DiligenceRail — the calm lane beside SuggestedResearch listing the
 * owner's diligence flags (autonomous-diligence SPR-01).
 *
 * One quiet row per flag: its kind, the optional note, and its status —
 * queued (the loop will pick it up) / spawned (being diligenced → the
 * LINKED investigation) / done / dismissed. Refs stay refs: a row NEVER
 * renders the raw object ref (copy-lint discipline — a node id is not a
 * label). Queued rows carry a small dismiss action (the operator's own
 * terminal); dismissing refetches. SPR-02/03 project spawned/done from the
 * daemon and the event log — until then a queued row reads as honestly
 * pending, and a spawned row already links its investigation from the
 * stored row.
 *
 * The rail refetches on mount, on window focus, and on the
 * diligence-changed signal any flag surface fires — same-tab convergence
 * without a store; the server row is the only truth.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  DILIGENCE_CHANGED_EVENT,
  dismissFlag,
  getQueue,
  notifyDiligenceChanged,
} from "../../api/diligence";
import type { DiligenceFlag, DiligenceQueueSummary } from "../../api/diligence";
import { ApiError } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import { kindLabel } from "../../shared/flagCopy";
import { LemonTag } from "../../components/lemon/LemonTag";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; flags: DiligenceFlag[]; summary: DiligenceQueueSummary | null }
  | { kind: "error"; reason: string | null };

export default function DiligenceRail() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const resp = await getQueue();
      setState({ kind: "ready", flags: resp.flags, summary: resp.summary });
    } catch (e) {
      setState({ kind: "error", reason: e instanceof ApiError ? e.body || null : null });
    }
  }, []);

  useEffect(() => {
    void load();
    const onChanged = () => void load();
    const onFocus = () => void load();
    window.addEventListener(DILIGENCE_CHANGED_EVENT, onChanged);
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener(DILIGENCE_CHANGED_EVENT, onChanged);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  return (
    <section
      aria-label="Your diligence queue"
      data-diligence-rail
      className="rounded-md border border-rule px-4 py-4 dark:border-charcoal-1"
    >
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="font-serif text-sm text-ink dark:text-bright">Your diligence queue</h2>
        <span className="font-mono text-xs text-shadow-1 dark:text-moonlight">
          flags the loop will pick up
        </span>
      </header>

      {/* SPR-03: the calm summary line — the numbers come from the budget
          sidecar + the event-log projection, never new counters. */}
      {state.kind === "ready" && state.summary && (
        <p
          className="mb-3 font-mono text-xs text-shadow-1 dark:text-moonlight"
          data-diligence-summary
        >
          {state.summary.diligenced_this_week}{" "}
          {state.summary.diligenced_this_week === 1
            ? "flag diligenced"
            : "flags diligenced"}{" "}
          this week · ${state.summary.spent_usd.toFixed(2)} of $
          {state.summary.cap_usd.toFixed(2)} daily cap
        </p>
      )}

      {state.kind === "loading" && (
        <p className="text-sm italic text-shadow-1 dark:text-moonlight" role="status">
          Reading your flags…
        </p>
      )}
      {state.kind === "error" && (
        <AIActionFailure
          title="Couldn’t read your diligence queue"
          reason={state.reason}
          onRetry={() => void load()}
        />
      )}
      {state.kind === "ready" && state.flags.length === 0 && (
        <p className="text-sm italic text-shadow-1 dark:text-moonlight">
          Nothing flagged yet — “flag for diligence” on an insight or open question puts it here.
        </p>
      )}
      {state.kind === "ready" && state.flags.length > 0 && (
        <ul className="space-y-1.5" data-diligence-rail-rows>
          {state.flags.map((f) => (
            <FlagRow key={f.flag_id} flag={f} />
          ))}
        </ul>
      )}
    </section>
  );
}

function FlagRow({ flag }: { flag: DiligenceFlag }) {
  const [busy, setBusy] = useState(false);

  async function dismiss() {
    setBusy(true);
    try {
      await dismissFlag(flag.flag_id);
      notifyDiligenceChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      data-diligence-row={flag.status}
      className="text-xs text-shadow-1 dark:text-moonlight"
    >
      <div className="flex items-baseline gap-2">
        <LemonTag colour={flag.status === "dismissed" ? "muted" : "sun"} className="text-xxs">
          {kindLabel(flag.kind)}
        </LemonTag>
        {flag.note ? (
          <span className="min-w-0 truncate font-serif text-ink dark:text-bright" title={flag.note}>
            {flag.note}
          </span>
        ) : (
          <span className="font-mono italic">flagged for the loop</span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-2 font-mono" data-diligence-row-status>
          {flag.status === "queued" && (
            <>
              <span>queued — the loop will pick it up</span>
              <button
                type="button"
                onClick={() => void dismiss()}
                disabled={busy}
                className="underline decoration-dotted underline-offset-2 hover:text-ink disabled:opacity-50 dark:hover:text-bright"
                title="Dismiss this flag (the object itself is untouched)"
              >
                {busy ? "dismissing…" : "dismiss"}
              </button>
            </>
          )}
          {flag.status === "spawned" &&
            (flag.spawned_investigation_id ? (
              <Link
                to={`/inv/${encodeURIComponent(flag.spawned_investigation_id)}`}
                className="text-sun-deep underline-offset-2 hover:underline dark:text-sun"
                data-diligence-spawned-link
              >
                being diligenced →
              </Link>
            ) : (
              <span>being diligenced</span>
            ))}
          {flag.status === "done" && (
            <span>
              diligenced
              {flag.outcome === "stopped"
                ? " — ended stopped"
                : flag.outcome === "failed"
                  ? " — failed"
                  : ""}
            </span>
          )}
          {flag.status === "dismissed" && <span>dismissed</span>}
        </span>
      </div>
      {/* SPR-03: what the daemon did and why — the row's receipt. */}
      {flag.status === "spawned" && flag.receipt?.kind === "spawned" && (
        <span
          className="block font-mono text-xxs text-shadow-2 dark:text-moonlight"
          data-diligence-receipt
        >
          reserved ${flag.receipt.reserve_usd?.toFixed(2)} · caps checked
        </span>
      )}
      {flag.status === "queued" && flag.receipt?.kind === "skipped" && (
        <span
          className="block font-mono text-xxs text-shadow-2 dark:text-moonlight"
          data-diligence-receipt
        >
          waiting — {flag.receipt.detail ?? flag.receipt.reason}
        </span>
      )}
    </li>
  );
}
