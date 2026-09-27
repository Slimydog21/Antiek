/**
 * DigDeeper — the island's chase composer (island SPR-04), opened INSIDE
 * the expanded card. The ChaseThread form's shape (passage quote prefilled,
 * question textarea) over the exact ChaseThread.tsx:90-127 launch sequence,
 * reused — one launch path, not two:
 *
 *   startInvestigation({
 *     question, context: spawnContext,
 *     parent_investigation_id: the island's thread,
 *     spawn_context: spawnContext,
 *     ...(reservedChildId ? { investigation_id: reservedChildId } : {}),
 *   }) → recordSpawnRelationship(child, parent) → celebrate.
 *
 * The no-orphan seam: a distilled question that carries a
 * reserved_child_investigation_id (the escalated flag on DistilledNode)
 * launches INTO the reserved id — every dig on that question targets the
 * same id, so a second dig can never mint a sibling duplicate.
 *
 * The launched chase appears in the island's family view immediately (the
 * caller refetches the SPR-01 family selector's source) with its own live
 * status; navigation stays the explicit jump ("open the chase →" / "Open
 * research"), matching the workstation chase — no island-specific fork.
 *
 * Deepen is the labelled budget ALTERNATIVE: "More budget on this same
 * thread" via steerResearch(…, "deepen"), rendered ONLY when the island
 * resolved the thread's live owning session (a non-terminal session state —
 * the thread is itself the session container, so session id = thread id).
 * A terminal or unresolvable session renders NO deepen option — never a
 * dead button; the chase remains. Each option states its cost semantics in
 * one line. Capacity warnings surface through the existing
 * startInvestigation path (its own toasts); a hard refusal lands in the
 * shared AIActionFailure.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import LemonButton from "../../../components/lemon/LemonButton";
import LemonTextarea from "../../../components/lemon/LemonTextarea";
import { ApiError, startInvestigation } from "../../../lib/api";
import { steerResearch, TERMINAL_STATES } from "../../../api/research";
import type { ResearchRunState } from "../../../api/research";
import { recordSpawnRelationship } from "../../../hooks/useInvestigationTree";
import AIActionFailure from "../../../shared/AIActionFailure";
import { CelebrateBurst, useCelebrate } from "../../../shared/delight";

export interface DigDeeperProps {
  /** The island's thread — the chase's DEFAULT parent (and the deepen
   *  steer target). */
  parentInvestigationId: string;
  /** The origin prefill (reading-global SPR-02): when the reader window was
   *  opened from a research, the chase parent PREFILLS to the investigation
   *  the operator came from — VISIBLE in the composer (never silent lineage
   *  metadata), and the launch still crosses the one existing path. */
  originChaseParent?: string | null;
  /** The chase seed: the anchor quote + the parent thread's question. The
   *  §9.0 boundary is upstream — a metadata-only anchor contributes position
   *  text, never a withheld sentence. */
  spawnContext: string;
  /** The textarea's initial question: the anchor quote for a bare dig, the
   *  distilled question's own text when digging on one. */
  initialQuestion: string;
  /** The no-orphan seam: launch INTO this reserved id when the dig is on an
   *  escalated distilled question; omit for a fresh child. Never rendered. */
  reservedChildId?: string | null;
  /** The deepen gate: the thread's resolved session state. null (or a
   *  terminal state) → the deepen option is ABSENT. */
  sessionState: ResearchRunState | null;
  /** Called with the child id after a successful chase launch (the island
   *  refetches the family so the chase shows immediately). */
  onLaunched: (childId: string) => void;
  /** Collapse the composer back to the card's action row. */
  onClose: () => void;
}

export default function DigDeeper({
  parentInvestigationId,
  originChaseParent = null,
  spawnContext,
  initialQuestion,
  reservedChildId,
  sessionState,
  onLaunched,
  onClose,
}: DigDeeperProps) {
  const [question, setQuestion] = useState(initialQuestion);
  const [busy, setBusy] = useState(false);
  const [launchedId, setLaunchedId] = useState<string | null>(null);
  const [error, setError] = useState<{ reason: string | null } | null>(null);
  const [deepen, setDeepen] = useState<"idle" | "busy" | "done" | "failed">("idle");
  const { celebrating, celebrate } = useCelebrate();
  // The chase's parent: the origin prefill when present, else the island's
  // thread (the default affordance — unchanged when origin is absent).
  const chaseParent = originChaseParent ?? parentInvestigationId;

  // The deepen gate: a resolved, LIVE owning session only. Terminal or
  // unresolvable → the option is absent (never a dead button).
  const deepenAvailable =
    launchedId === null && sessionState !== null && !TERMINAL_STATES.has(sessionState);

  async function follow() {
    const q = question.trim();
    if (q.length < 3) {
      setError({ reason: "There’s nothing here to follow yet." });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await startInvestigation({
        question: q,
        context: spawnContext,
        parent_investigation_id: chaseParent,
        spawn_context: spawnContext,
        // Consume the reserved escalation id when the dig carries one; omit
        // it otherwise so the substrate mints a fresh child. Every dig on an
        // escalated question targets the SAME reserved id — a second dig
        // can never mint a sibling duplicate.
        ...(reservedChildId ? { investigation_id: reservedChildId } : {}),
      });
      setLaunchedId(resp.investigation_id);
      recordSpawnRelationship(resp.investigation_id, chaseParent);
      onLaunched(resp.investigation_id);
      // The payoff is already in hand (the id is back); the beat just
      // decorates it — non-blocking, fires once, same hook as the
      // workstation chase.
      celebrate();
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setError({ reason });
    } finally {
      setBusy(false);
    }
  }

  async function deepenThisThread() {
    setDeepen("busy");
    try {
      // The island's thread is itself the session container (useIslandThread's
      // resolution rule), so session id = investigation id.
      await steerResearch(parentInvestigationId, parentInvestigationId, "deepen");
      setDeepen("done");
    } catch {
      setDeepen("failed");
    }
  }

  const onFollow = () => {
    void follow();
  };

  if (launchedId) {
    return (
      <div data-dig-deeper data-dig-launched className="mb-2 border-t border-hairline pt-2">
        <p className="text-shadow-1 dark:text-moonlight mb-1.5" role="status">
          following the thread… — the chase is in the family above
        </p>
        <div className="flex items-center gap-2">
          <Link
            to={`/inv/${encodeURIComponent(launchedId)}`}
            className="text-sun-deep underline-offset-2 hover:underline"
            data-dig-open-chase
          >
            open the chase →
          </Link>
          <CelebrateBurst active={celebrating} size={32} />
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-shadow-1 hover:text-ink dark:hover:text-bright"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <div data-dig-deeper className="mb-2 border-t border-hairline pt-2">
      <label className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1">
        Following from this passage
      </label>
      {originChaseParent ? (
        <p
          className="text-xxs font-mono text-sun-deep dark:text-sun mb-1"
          data-dig-origin
        >
          chasing from the research you came from
        </p>
      ) : null}
      <blockquote
        data-dig-quote
        className="font-serif italic text-ink-soft dark:text-starlight border-l-edge border-sun pl-2 mb-2 line-clamp-3"
      >
        “{spawnContext}”
      </blockquote>
      <LemonTextarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        disabled={busy}
        minRows={3}
        maxRows={8}
        onSubmit={onFollow}
        className="font-serif"
        aria-label="What do you want to find out?"
      />
      {/* The cost semantics, one line each — stated before the click. */}
      <p className="text-xxs text-shadow-1 dark:text-moonlight mt-1" data-dig-chase-cost>
        Follow this — a new child investigation, its own budget.
      </p>

      {error && (
        <AIActionFailure
          title="Couldn’t follow this thread"
          reason={error.reason}
          onRetry={onFollow}
          retryLabel="Try again"
        />
      )}

      <div className="flex items-center justify-end gap-2 mt-2">
        <button
          type="button"
          onClick={onClose}
          className="text-shadow-1 hover:text-ink dark:hover:text-bright"
        >
          Cancel
        </button>
        <CelebrateBurst active={celebrating} size={32} />
        <LemonButton
          variant="primary"
          size="sm"
          onClick={onFollow}
          disabled={busy || question.trim().length < 3}
        >
          {busy ? "Following…" : "Follow this"}
        </LemonButton>
      </div>

      {deepenAvailable ? (
        <div className="mt-2 border-t border-hairline pt-2" data-dig-deepen>
          <button
            type="button"
            onClick={() => void deepenThisThread()}
            disabled={deepen === "busy" || deepen === "done"}
            className="text-sun-deep underline-offset-2 hover:underline disabled:opacity-50"
          >
            {deepen === "busy"
              ? "Adding budget…"
              : deepen === "done"
                ? "Budget added — the thread continues"
                : "More budget on this same thread"}
          </button>
          <p className="text-xxs text-shadow-1 dark:text-moonlight" data-dig-deepen-cost>
            Deepen — the same investigation, more budget.
          </p>
          {deepen === "failed" ? (
            <p className="text-xxs text-emperor" role="alert">
              The deepen steer was refused — the chase above remains.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
