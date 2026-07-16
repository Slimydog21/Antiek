import { useEffect, useMemo, useState } from "react";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { challengeNote, ApiError } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import NoteHistoryDisclosure from "./NoteHistoryDisclosure";

/**
 * NotesPanel — auto-notes appearing as the research runs (SPR-03 M1 + M3).
 *
 * What it is: a READ/DISPLAY layer over `investigation.events`, the same
 * already-deduped stream `useInvestigation` feeds the thinking stream. As the
 * async note-taker's `note.emerged` / `question.identified` land, they appear
 * here beside the narration — the user watches notes being TAKEN, not just
 * activity narrated. It introduces no second writer and emits no event of its
 * own; the one mutation (a challenge) goes through the backend living-note
 * path (POST .../challenge), which serializes through runtime/db_lock.
 *
 * Living note (M3): a `note.emerged` followed by `note.refined` events for the
 * same note resolves to ONE row whose text is the latest authoritative outcome — the note
 * changed in place, it did not duplicate. The prior text is recoverable (the
 * refined event carries previous→new), surfaced behind a "see what changed"
 * toggle. The backend decides each outcome; this view validates its complete
 * authority tuple and folds only a coherent sequence chain.
 *
 * Reconnect idempotency (M1 gate): notes are keyed by note id and refinements
 * collapse onto their origin note, so a reconnect that re-delivers events the client
 * already saw yields the same rows — no doubled note after a dropped socket.
 */

/** One note as the panel renders it, after collapsing refinements. */
export interface LiveNote {
  noteId: string;
  kind: "insight" | "question";
  /** Current text — the latest refinement if the note is living. */
  text: string;
  /** Immutable wording captured by this source-local observation. */
  observationText: string;
  /** The text before the most recent refinement, when one happened. */
  previousText: string | null;
  confidence: string | null;
  /** node_id when the note was mirrored to the graph (challengeable). null
   *  when the note has no graph node yet — challenge is then unavailable. */
  nodeId: string | null;
  /** How many times this note's text has changed (living-note signal). */
  refinements: number;
  /** Highest authoritative applied sequence folded into this row. */
  lastAppliedSequence: number | null;
  /** Only model-emerged notes may receive note.refined outcomes. */
  refinementEligible: boolean;
  /**
   * §9 provenance discriminator. "user" for a note the reader authored (an
   * in-book FloatMenu marginalia note); null for a model-distilled note
   * (note.emerged / question.identified — the absence IS "model"). The
   * surface uses this to label a user note honestly and to NEVER conflate it
   * with a model-emerged one.
   */
  sourceKind: "user" | null;
}

/**
 * Collapse the event stream into the current set of notes. Pure + total so it
 * is unit-testable and so a reconnect (duplicate events) is idempotent.
 *
 * Insights/questions arrive as `note.emerged` / `question.identified`. A
 * Complete outcomes attach through origin identity and a coherent sequence
 * chain. Applied outcomes contribute new text; superseded outcomes contribute
 * authoritative prior text. Legacy, malformed, conflicting, and unattached
 * attempts remain audit evidence and do not become visible notes.
 */
export function deriveNotes(events: Event[]): LiveNote[] {
  const byId = new Map<string, LiveNote>();
  const order: string[] = [];
  const seenEvents = new Set<string>();
  const nodeSequences = new Map<string, number>();
  const nodeCanonicalTexts = new Map<string, string>();
  const nodePreviousTexts = new Map<string, string>();
  const nodeRefinementCounts = new Map<string, number>();

  for (const e of events) {
    const id = e.event_id;
    if (id && seenEvents.has(id)) continue; // reconnect dup — count once
    if (id) seenEvents.add(id);
    const p = (e.payload ?? {}) as unknown as Record<string, unknown>;

    if (e.action_type === "note.emerged") {
      const noteId = asStr(p.note_id);
      const observationText = asStr(p.note_text);
      if (!noteId || !observationText) continue;
      const prior = byId.get(noteId);
      if (prior) continue;
      const nodeId = asStr(p.node_id);
      order.push(noteId);
      byId.set(noteId, {
        noteId,
        kind: "insight",
        text: (nodeId && nodeCanonicalTexts.get(nodeId)) ?? observationText,
        observationText,
        previousText: (nodeId && nodePreviousTexts.get(nodeId)) ?? null,
        confidence: asStr(p.confidence),
        nodeId,
        refinements: nodeId ? (nodeRefinementCounts.get(nodeId) ?? 0) : 0,
        lastAppliedSequence: nodeId ? (nodeSequences.get(nodeId) ?? null) : null,
        refinementEligible: true,
        // A distilled note has no source_kind — the absence is "model".
        sourceKind: null,
      });
    } else if (e.action_type === "marginalia.noted") {
      // Read SPR-07 M3 — an in-book FloatMenu NOTE. The reader highlighted a
      // passage and authored a note; it is a USER-sourced per-book insight.
      // The note text is what they wrote (note_text), the highlighted span
      // (excerpt) is its anchor. §9: source_kind is pinned "user" on the
      // event, carried here, and NEVER conflated with a model-emerged note.
      const noteId = asStr(p.note_id);
      const text = asStr(p.note_text);
      if (!noteId || !text) continue;
      const prior = byId.get(noteId);
      if (prior) continue;
      order.push(noteId);
      byId.set(noteId, {
        noteId,
        kind: "insight",
        text,
        observationText: text,
        previousText: null,
        confidence: null,
        // The in-book note's graph node is content-addressed off its text and
        // promoted host-side; the event itself carries no node_id, so the
        // challenge affordance stays unavailable until a node_id is observed.
        nodeId: null,
        refinements: 0,
        lastAppliedSequence: null,
        refinementEligible: false,
        sourceKind: "user",
      });
    } else if (e.action_type === "question.identified") {
      const noteId = asStr(p.question_id);
      const text = asStr(p.question_text);
      if (!noteId || !text) continue;
      const prior = byId.get(noteId);
      if (prior) continue;
      order.push(noteId);
      byId.set(noteId, {
        noteId,
        kind: "question",
        text,
        observationText: text,
        previousText: null,
        confidence: null,
        nodeId: null,
        refinements: 0,
        lastAppliedSequence: null,
        refinementEligible: false,
        sourceKind: null,
      });
    } else if (e.action_type === "note.refined") {
      const noteId = asStr(p.origin_note_id);
      const graphNodeId = asStr(p.note_id);
      const newText = asStr(p.new_text);
      const prevText = asStr(p.previous_text);
      const sequence = asNonNegativeInt(p.sequence);
      const previousSequence = asPreviousSequence(p.previous_sequence);
      const outcome = p.outcome;
      if (
        (outcome !== "applied" && outcome !== "superseded") ||
        !noteId || !graphNodeId || !newText || !prevText ||
        sequence === null || previousSequence === null ||
        (outcome === "applied" ? sequence <= previousSequence : sequence > previousSequence)
      ) continue;
      const existing = byId.get(noteId);
      if (!existing) {
        // Without the emerged note, provenance and graph identity are unknown.
        // The durable event remains available in audit history; this fold does
        // not invent a standalone note from an unattached outcome.
        continue;
      }
      const knownCanonicalText = nodeCanonicalTexts.get(graphNodeId);
      if (
        !existing.refinementEligible ||
        (existing.nodeId !== null && existing.nodeId !== graphNodeId) ||
        (nodeSequences.has(graphNodeId) && previousSequence !== nodeSequences.get(graphNodeId)) ||
        // An applied transition must start at the text this fold already
        // knows. A superseded attempt may only restate established canonical
        // truth; it cannot bootstrap arbitrary text from an unseen history.
        (outcome === "applied" && prevText !== (knownCanonicalText ?? existing.text)) ||
        (outcome === "superseded" && (knownCanonicalText === undefined || prevText !== knownCanonicalText))
      ) {
        continue;
      }
      if (outcome === "superseded") {
        nodeCanonicalTexts.set(graphNodeId, prevText);
        for (const [aliasId, alias] of byId) {
          if (aliasId !== noteId && alias.nodeId !== graphNodeId) continue;
          if (!alias.refinementEligible) continue;
          byId.set(aliasId, {
            ...alias,
            text: prevText,
            nodeId: graphNodeId,
            lastAppliedSequence: previousSequence,
          });
        }
        nodeSequences.set(graphNodeId, previousSequence);
        continue;
      }
      const refinementCount = (nodeRefinementCounts.get(graphNodeId) ?? 0) + 1;
      nodeCanonicalTexts.set(graphNodeId, newText);
      nodePreviousTexts.set(graphNodeId, prevText);
      nodeRefinementCounts.set(graphNodeId, refinementCount);
      for (const [aliasId, alias] of byId) {
        if (aliasId !== noteId && alias.nodeId !== graphNodeId) continue;
        if (!alias.refinementEligible) continue;
        byId.set(aliasId, {
          ...alias,
          previousText: prevText,
          text: newText,
          nodeId: graphNodeId,
          refinements: refinementCount,
          lastAppliedSequence: sequence,
        });
      }
      nodeSequences.set(graphNodeId, sequence);
    }
  }

  return order.map((id) => byId.get(id)!).filter(Boolean);
}

function asStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function asNonNegativeInt(v: unknown): number | null {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= 0 ? v : null;
}

function asPreviousSequence(v: unknown): number | null {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= -1 ? v : null;
}

export interface NotesPanelProps {
  investigation: InvestigationState;
}

export default function NotesPanel({ investigation }: NotesPanelProps) {
  const notes = useMemo(() => deriveNotes(investigation.events), [investigation.events]);
  const running = investigation.status === "in_progress";

  if (notes.length === 0) {
    return (
      <div className="px-4 py-6 text-sm font-serif text-ink-mute dark:text-moonlight">
        {running
          ? "Notes will appear here as the research reads and thinks."
          : "No notes were taken for this research yet."}
      </div>
    );
  }

  return (
    <ol className="space-y-2.5 px-4 py-4">
      {notes.map((n) => (
        <NoteRow key={n.noteId} note={n} investigationId={investigation.id} />
      ))}
    </ol>
  );
}

/** The outcome of a challenge, shown beneath the note it acted on. */
type ChallengeState =
  | { kind: "idle" }
  | { kind: "busy" }
  | { kind: "changed"; newText: string; baseText: string; baseSequence: number | null }
  | { kind: "unchanged" } // a stale refinement lost the seq race
  | { kind: "escalated" }
  | { kind: "noModel" }
  | { kind: "error"; detail: string };

function NoteRow({ note, investigationId }: { note: LiveNote; investigationId: string }) {
  const [showObservation, setShowObservation] = useState(false);
  const [challenge, setChallenge] = useState<ChallengeState>({ kind: "idle" });
  const [challengeKey, setChallengeKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (
      challenge.kind === "changed" &&
      (note.text !== challenge.baseText || note.lastAppliedSequence !== challenge.baseSequence)
    ) {
      setChallenge({ kind: "idle" });
    }
  }, [challenge, note.lastAppliedSequence, note.text]);

  const challengeIsCurrent = challenge.kind !== "changed" || (
    note.text === challenge.baseText &&
    note.lastAppliedSequence === challenge.baseSequence
  );
  const visibleChallenge: ChallengeState = challengeIsCurrent
    ? challenge
    : { kind: "idle" };

  // Render the live text — the refined text when the note is living. After a
  // successful challenge, the next note.refined event re-derives this; the
  // local "changed" beat is the immediate feedback before that lands.
  const text = visibleChallenge.kind === "changed"
    ? visibleChallenge.newText
    : note.text;

  const runChallenge = async () => {
    if (!note.nodeId) return;
    setChallenge({ kind: "busy" });
    try {
      const res = await challengeNote(note.nodeId, {
        investigation_id: investigationId,
        idempotency_key: challengeKey,
        origin_note_id: note.noteId,
      });
      if (res.applied && res.new_text) {
        setChallengeKey(crypto.randomUUID());
        setChallenge({
          kind: "changed",
          newText: res.new_text,
          baseText: note.text,
          baseSequence: note.lastAppliedSequence,
        });
      } else if (res.escalated) {
        setChallengeKey(crypto.randomUUID());
        setChallenge({ kind: "escalated" });
      } else if (res.superseded) {
        setChallengeKey(crypto.randomUUID());
        setChallenge({ kind: "unchanged" });
      } else {
        setChallenge({ kind: "idle" });
      }
    } catch (e) {
      // 503 = no model configured → the honest no-key state, not an error blob.
      if (e instanceof ApiError && e.status === 503) {
        setChallenge({ kind: "noModel" });
      } else {
        setChallenge({ kind: "error", detail: e instanceof Error ? e.message : "unknown" });
      }
    }
  };
  // The click handler must not hand React a floating promise — own it here so
  // a rejection is fully inside this component's try/catch.
  const onChallenge = () => {
    void runChallenge();
  };

  return (
    <li className="flex flex-col gap-1.5 border-b border-rule pb-2.5 last:border-b-0 dark:border-charcoal-1">
      <div className="flex items-start gap-2.5">
        <span
          className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${
            note.kind === "question" ? "bg-sun-deep dark:bg-sun" : "bg-aurora"
          }`}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
            {note.kind === "question" ? <span className="italic">Open question: </span> : null}
            {text}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
            {note.confidence && note.kind === "insight" && (
              <span className="font-mono">{confidenceWord(note.confidence)}</span>
            )}
            {note.observationText !== note.text && (
              <button
                type="button"
                onClick={() => setShowObservation((value) => !value)}
                className="font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
              >
                {showObservation ? "hide observed wording" : "see observed wording"}
              </button>
            )}
            {note.nodeId && note.refinements > 0 && (
              <NoteHistoryDisclosure
                nodeId={note.nodeId}
                investigationId={investigationId}
                refinementCount={note.refinements}
              />
            )}
            {note.nodeId && challenge.kind !== "busy" && (
              <button
                type="button"
                onClick={onChallenge}
                className="font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
              >
                challenge this
              </button>
            )}
            {challenge.kind === "busy" && (
              <span className="font-mono italic" role="status">weighing the challenge…</span>
            )}
          </div>

          {showObservation && note.observationText !== note.text && (
            <p className="mt-1.5 border-l-2 border-rule pl-2 font-serif text-[12px] italic leading-relaxed text-ink-mute dark:border-charcoal-1 dark:text-moonlight">
              observed as: {note.observationText}
            </p>
          )}

          <ChallengeOutcome state={visibleChallenge} onRetry={onChallenge} />
        </div>
      </div>
    </li>
  );
}

/** The plain-language result of a challenge, beneath the note. */
function ChallengeOutcome({ state, onRetry }: { state: ChallengeState; onRetry: () => void }) {
  if (state.kind === "changed") {
    return (
      <p className="mt-1.5 font-mono text-[11px] text-emerald-700" role="status">
        the note changed in light of your challenge
      </p>
    );
  }
  if (state.kind === "unchanged") {
    return (
      <p className="mt-1.5 font-mono text-[11px] text-shadow-1 dark:text-moonlight" role="status">
        a newer revision already settled this — the note is unchanged
      </p>
    );
  }
  if (state.kind === "escalated") {
    return (
      <p className="mt-1.5 font-mono text-[11px] text-sun-deep dark:text-sun" role="status">
        this needs more research — saved as an open question to chase
      </p>
    );
  }
  if (state.kind === "noModel") {
    return (
      <div className="mt-1.5">
        <AIActionFailure
          title="Couldn’t weigh the challenge"
          reason={null}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mt-1.5">
        <AIActionFailure
          title="Couldn’t weigh the challenge"
          reason={state.detail}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      </div>
    );
  }
  return null;
}

/** A confidence word a reader understands — never the raw enum token. */
function confidenceWord(confidence: string): string {
  switch (confidence) {
    case "high":
      return "well-grounded";
    case "moderate":
      return "fairly grounded";
    case "low":
      return "lightly grounded";
    default:
      return "grounding unclear";
  }
}
