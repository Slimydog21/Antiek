import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getSuggestions, type Suggestion } from "../../api/research";
import { startInvestigation, ApiError } from "../../lib/api";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import AIActionFailure from "../../shared/AIActionFailure";
import LemonButton from "../../components/lemon/LemonButton";
import { LemonTag } from "../../components/lemon/LemonTag";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * SuggestedResearch — the §7 compounding flywheel, surfaced (SPR-09).
 *
 * The continuous daemon already scans every prior research for unresolved
 * evidentiary gaps, scores them, and (within its §7.4 caps) chases the best.
 * That loop ran in the dark. This surface reads the daemon's EXISTING output
 * and offers the top gaps as plain-language "threads worth chasing", where the
 * user already works: a calm lane in the monitor (SPR-05) and beside the
 * answer (SPR-04). It does not re-score, re-architect, or re-run anything.
 *
 * The three load-bearing properties (each enforced here + tested):
 *
 * 1. **Surfacing adds no spend.** Mounting fetches suggestions with a plain
 *    read (`getSuggestions` → `GET /research/suggestions`, read-only on the
 *    server). Rendering launches NOTHING. A suggestion costs nothing until the
 *    user clicks "Chase this" — there is no auto-launch, no timer, no
 *    "top suggestion fires itself" (the rejected alternative — see the sprint
 *    page's rigor #2). This is consistent with §2.6's curiosity-gated posture:
 *    the surface offers; it does not auto-spend.
 *
 * 2. **Launch = the existing capped path.** A chase goes through the SAME
 *    budget-capped launch SPR-01 / ChaseThread use: when a parent research is
 *    in context (the answer side), we hand the suggestion to the caller's
 *    chase gesture (`onChase`) so it opens the one ChaseThread panel; with no
 *    parent (the monitor lane) we call `startInvestigation` directly — the
 *    same per-investigation-capped runner, no special unbounded path.
 *
 * 3. **A proposal, not in-flight.** A suggestion is visually + semantically
 *    DISTINCT from a running research: a dashed-edge offer card with a "could
 *    chase" tag, never the solid running-research row. Once chased in-session,
 *    its key is dropped from the list (client dedupe on top of the server's
 *    underlying-question dedupe) so it isn't offered twice.
 *
 * Honest no-key / no-daemon (M4): with no provider keys the daemon can't run,
 * so it produces no gaps and the server returns an empty list; we render the
 * shared `AIActionFailure` no-result state — never a fabricated thread. A fetch
 * error (substrate down) shows the same honest surface with the engine reason.
 *
 * No daemon vocabulary crosses into the copy: "thread worth chasing", not
 * "evidentiary gap"; "found across N researches", not "co-occurrence"; the
 * dedupe `key` and any id are opaque handles, never rendered.
 */

export type SuggestedChase = {
  /** The suggestion's plain-language question — what the chase will pursue. */
  text: string;
  /** The opaque dedupe key, echoed so the caller can drop it once chased. */
  key: string;
};

type Props = {
  /**
   * Where this surface lives, which only changes the framing copy + density:
   *  - "lane"   — the calm "what to chase next" lane in the monitor (SPR-05).
   *  - "beside" — a compact offer beside a single answer (SPR-04).
   */
  variant?: "lane" | "beside";
  /**
   * The chase gesture to reuse when a parent research is in context (the
   * answer side). Given ⇒ a click hands the suggestion to the caller (which
   * opens the one ChaseThread panel, the SPR-04 gesture) instead of launching
   * a standalone research here. Absent ⇒ the monitor lane launches a
   * standalone research through `startInvestigation` (the same capped path).
   */
  onChase?: (chase: SuggestedChase) => void;
  /** Whether the user can launch at all (disabled when unauthenticated). */
  canLaunch?: boolean;
  /** How many suggestions to request (display cap; default the server's 8). */
  limit?: number;
};

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; suggestions: Suggestion[] }
  | { kind: "error"; reason: string | null };

export default function SuggestedResearch({
  variant = "lane",
  onChase,
  canLaunch = true,
  limit = 8,
}: Props) {
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // Keys chased in this session — dropped from the offered list so a thread
  // the user just pulled isn't offered again before the next server refresh.
  const [chasedKeys, setChasedKeys] = useState<Set<string>>(() => new Set());

  const load = useCallback(() => {
    let live = true;
    setState({ kind: "loading" });
    // READ-ONLY: a plain GET. No launch, no spend — see the file header.
    void getSuggestions(limit)
      .then((resp) => {
        if (live) setState({ kind: "ready", suggestions: resp.suggestions });
      })
      .catch((e) => {
        if (!live) return;
        const reason = e instanceof ApiError ? e.body || null : null;
        setState({ kind: "error", reason });
      });
    return () => {
      live = false;
    };
  }, [limit]);

  useEffect(() => load(), [load]);

  const markChased = useCallback((key: string) => {
    setChasedKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }, []);

  if (state.kind === "loading") {
    return (
      <Frame variant={variant}>
        <p className="text-sm italic text-shadow-1 dark:text-moonlight">
          Looking for threads worth chasing…
        </p>
      </Frame>
    );
  }

  if (state.kind === "error") {
    return (
      <Frame variant={variant}>
        <AIActionFailure
          title="Couldn’t look for threads to chase"
          reason={state.reason}
          onRetry={load}
        />
      </Frame>
    );
  }

  const offered = state.suggestions.filter((s) => !chasedKeys.has(s.key));

  if (offered.length === 0) {
    // Honest no-daemon / no-key state: the daemon produced no gaps (no keys,
    // never ran) — say so plainly, never invent a thread. Reuses the shared
    // no-result sentence (no `reason` ⇒ the no-provider branch).
    return (
      <Frame variant={variant}>
        <AIActionFailure
          title="No threads to chase yet"
          onRetry={load}
          retryLabel="Look again"
        />
      </Frame>
    );
  }

  return (
    <Frame variant={variant}>
      <div className={variant === "beside" ? "space-y-2" : "space-y-3"}>
        {offered.map((s) => (
          <SuggestionCard
            key={s.key}
            suggestion={s}
            canLaunch={canLaunch}
            onChaseGesture={onChase}
            onLaunched={(childId) => {
              markChased(s.key);
              if (childId) navigate(`/inv/${encodeURIComponent(childId)}`);
            }}
          />
        ))}
      </div>
    </Frame>
  );
}

function Frame({
  variant,
  children,
}: {
  variant: "lane" | "beside";
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label="Suggested next researches"
      className={
        variant === "beside"
          ? "px-4 py-4"
          : "rounded-md border border-rule px-4 py-4 dark:border-charcoal-1"
      }
    >
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="font-serif text-sm text-ink dark:text-bright">
          {variant === "beside" ? "Threads worth chasing" : "Suggested next"}
        </h2>
        <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          {variant === "beside"
            ? "open questions the loop found across your research"
            : "from the open questions across your research"}
        </span>
      </header>
      {children}
    </section>
  );
}

function SuggestionCard({
  suggestion,
  canLaunch,
  onChaseGesture,
  onLaunched,
}: {
  suggestion: Suggestion;
  canLaunch: boolean;
  onChaseGesture?: (chase: SuggestedChase) => void;
  onLaunched: (childId: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ reason: string | null } | null>(null);

  const chase = useCallback(async () => {
    // Living-TV: every chase offer spend is a deep-research start beat.
    emitWernerExperience("deep_research_start");
    // Hand off to the caller's chase gesture when a parent is in context —
    // one launch path, the SPR-04 ChaseThread panel. The caller owns the
    // explicit-click launch + dedupe there; we just mark it chased.
    if (onChaseGesture) {
      onChaseGesture({ text: suggestion.question, key: suggestion.key });
      onLaunched(null);
      return;
    }
    // The monitor lane: no parent → launch a standalone research through the
    // SAME capped path SPR-01 uses (`startInvestigation`). Explicit click
    // only; this is the one spend in the whole sprint.
    setBusy(true);
    setError(null);
    try {
      const resp = await startInvestigation({
        question: suggestion.question,
        context: suggestion.suggested_retrieval ?? "",
        ...(suggestion.source_investigation_id
          ? { parent_investigation_id: suggestion.source_investigation_id }
          : {}),
      });
      if (suggestion.source_investigation_id) {
        recordSpawnRelationship(resp.investigation_id, suggestion.source_investigation_id);
      }
      onLaunched(resp.investigation_id);
    } catch (e) {
      emitWernerExperience("deep_research_error");
      const reason = e instanceof ApiError ? e.body || null : null;
      setError({ reason });
    } finally {
      setBusy(false);
    }
  }, [onChaseGesture, onLaunched, suggestion]);

  return (
    <article
      // DISTINCT from a running-research row: a dashed-edge offer card, not a
      // solid in-flight row. The dashed border is the "this is a proposal, not
      // running" signal (rigor #3 + the distinction gate).
      data-testid="suggestion-card"
      className="rounded-md border border-dashed border-rule bg-ice-1/40 px-3 py-2.5 dark:border-charcoal-1 dark:bg-charcoal-1/30"
    >
      <div className="mb-1.5 flex items-center gap-2">
        <LemonTag colour="muted" className="text-[10px]">
          could chase
        </LemonTag>
        {suggestion.seen_in_research_count > 1 && (
          <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
            found across {suggestion.seen_in_research_count} of your researches
          </span>
        )}
      </div>
      <p className="font-serif text-sm leading-relaxed text-ink dark:text-bright">
        {suggestion.question}
      </p>
      {suggestion.suggested_retrieval && (
        <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          worth looking at: {suggestion.suggested_retrieval}
        </p>
      )}

      {error && (
        <div className="mt-2">
          <AIActionFailure
            title="Couldn’t chase this thread"
            reason={error.reason}
            onRetry={() => void chase()}
          />
        </div>
      )}

      <div className="mt-2 flex items-center justify-end">
        <LemonButton
          variant="secondary"
          size="sm"
          onClick={() => void chase()}
          disabled={busy || !canLaunch}
          title={canLaunch ? undefined : "Sign in to chase a thread."}
        >
          {busy ? "Chasing…" : "Chase this"}
        </LemonButton>
      </div>
    </article>
  );
}
