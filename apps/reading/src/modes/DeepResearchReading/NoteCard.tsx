/**
 * DRW SPR-10 M4 — living-note challenge.
 *
 * A note (insight or open question) the system distilled. The reader can
 * challenge it: providing a correction REFINES the note in place (SPR-03
 * note.refined — no duplicate); leaving the correction blank ESCALATES (the
 * graph can't resolve it) and surfaces the spin-research affordance, handing
 * the reserved child investigation to the caller. Either way the note never
 * silently absorbs an unverified change.
 */

import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { challengeNote, type ChallengeResult, type DocumentNote } from "../../api/reading";

export interface NoteCardProps {
  note: DocumentNote;
  documentId: string;
  stale?: boolean;
  /** Called after a refine so the parent can refresh the note text. */
  onRefined?: (newText: string) => void;
  /** Called when a challenge escalates — the reserved child investigation is
   * the spin-research seam. */
  onEscalated?: (reservedChildInvestigationId: string, questionId: string) => void;
}

export default function NoteCard({ note, documentId, stale, onRefined, onEscalated }: NoteCardProps) {
  const [open, setOpen] = useState(false);
  const [challenge, setChallenge] = useState("");
  const [correction, setCorrection] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState(note.text);

  const submit = async () => {
    if (!challenge.trim()) return;
    setBusy(true);
    try {
      const res: ChallengeResult = await challengeNote(note.node_id, {
        challenge_text: challenge.trim(),
        document_id: documentId,
        resolution: correction.trim() || undefined,
      });
      if (res.applied && res.new_text) {
        setText(res.new_text);
        onRefined?.(res.new_text);
      } else if (res.escalated && res.reserved_child_investigation_id) {
        onEscalated?.(res.reserved_child_investigation_id, res.escalated_question_id ?? "");
      }
      setOpen(false);
      setChallenge("");
      setCorrection("");
    } finally {
      setBusy(false);
    }
  };

  const tag = note.kind === "insight" ? "INSIGHT" : "OPEN QUESTION";
  const tagClass = note.kind === "insight" ? "text-sun-deep" : "text-aurora";

  return (
    <article className="flex flex-col gap-2 rounded-md border-2 border-sun bg-ice-0 p-3 dark:bg-charcoal-2">
      <div className="flex items-center justify-between">
        <span className={`text-[10px] font-semibold uppercase tracking-[0.12em] ${tagClass}`}>{tag}</span>
        <span className="text-[10px] uppercase tracking-[0.1em] text-shadow-1 dark:text-moonlight">
          {note.confidence}
          {stale && <span className="ml-2 text-emperor" title="anchor no longer in the document">stale anchor</span>}
        </span>
      </div>
      <p className="text-sm text-ink dark:text-bright">{text}</p>
      {!open ? (
        <button
          className="self-start text-[11px] text-shadow-1 hover:text-aurora dark:text-moonlight"
          onClick={() => setOpen(true)}
        >
          challenge this note
        </button>
      ) : (
        <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <input
            className="rounded border border-ice-4 bg-ice-1 px-2 py-1 text-xs text-ink dark:border-slate-2 dark:bg-charcoal-1 dark:text-bright"
            placeholder="What's wrong / what to question…"
            value={challenge}
            onChange={(e) => setChallenge(e.target.value)}
            aria-label="challenge text"
          />
          <input
            className="rounded border border-ice-4 bg-ice-1 px-2 py-1 text-xs text-ink dark:border-slate-2 dark:bg-charcoal-1 dark:text-bright"
            placeholder="Correction (refines the note) — leave blank to escalate to a research"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            aria-label="correction text"
          />
          <div className="flex gap-1.5">
            <LemonButton size="sm" variant="primary" type="submit" disabled={busy || !challenge.trim()}>
              {correction.trim() ? "Refine" : "Escalate → research"}
            </LemonButton>
            <LemonButton size="sm" variant="tertiary" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </LemonButton>
          </div>
        </form>
      )}
    </article>
  );
}
