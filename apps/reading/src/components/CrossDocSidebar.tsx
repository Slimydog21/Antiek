import { useMemo } from "react";

import type {
  CrossDocQuestionAnsweredPayload,
  Event,
  QuestionIdentifiedPayload,
} from "../generated/types";
import { emitWernerExperience } from "../werner/reactionBus";

interface CrossDocSidebarProps {
  events: Event[];
  /** Optional click handler — when the operator clicks a question_id
   *  or note_id link, the parent can scroll/jump to that event. */
  onCiteJump?: (eventId: string) => void;
}

/**
 * Live feed of cross-document question→answer links.
 *
 * Renders one card per ``cross_doc.question_answered`` event:
 * - Original question text (looked up from the matching
 *   ``question.identified`` event).
 * - Source document → answer document arrow.
 * - Bridging note_id link (clickable to scroll to the note that
 *   resolved the cross-doc question).
 *
 * The operator's Sprint 1 differentiator: "questions via note taking
 * on documents and the process of searching for an intellectually
 * honest, fair, diligent, rigorous, and defensible answer." Sprint 5
 * day 1-2 makes the resolved links visible — they've been firing into
 * the trajectory since Sprint 4 day 2-3.
 */
export default function CrossDocSidebar({
  events,
  onCiteJump,
}: CrossDocSidebarProps) {
  // Lookup table: question_id → question_text (from question.identified
  // events). Lets the card show the original question even though the
  // CrossDoc payload only carries the question_id.
  const questionTextById = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of events) {
      if (e.action_type === "question.identified") {
        const p = e.payload as QuestionIdentifiedPayload;
        map.set(p.question_id, p.question_text);
      }
    }
    return map;
  }, [events]);

  const links = useMemo(
    () =>
      events.filter(
        (e): e is Event & { payload: CrossDocQuestionAnsweredPayload } =>
          e.action_type === "cross_doc.question_answered",
      ),
    [events],
  );

  return (
    <div className="flex flex-col h-full bg-ice-0 dark:bg-charcoal-2 border-l border-rule dark:border-charcoal-1">
      <div className="px-4 py-2 text-xs font-mono bg-ice-3 dark:bg-charcoal-1 border-b border-rule dark:border-charcoal-1 flex items-center justify-between">
        <span className="text-ink-soft dark:text-starlight">cross-doc</span>
        <span className="text-shadow-1 dark:text-moonlight">
          {links.length} link{links.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="flex-1 overflow-auto px-3 py-3">
        {links.length === 0 ? (
          <div className="text-sm text-ink-mute dark:text-moonlight font-mono leading-relaxed">
            <p>no cross-doc links yet.</p>
            <p className="mt-1">
              when a note that emerges on one document answers an open
              question raised on another, the link appears here.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {links.map((e) => (
              <CrossDocCard
                key={e.event_id}
                event={e}
                questionText={questionTextById.get(e.payload.question_id)}
                onCiteJump={onCiteJump}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CrossDocCard({
  event,
  questionText,
  onCiteJump,
}: {
  event: Event & { payload: CrossDocQuestionAnsweredPayload };
  questionText: string | undefined;
  onCiteJump?: (eventId: string) => void;
}) {
  const p = event.payload;
  return (
    <li className="border border-violet-200 rounded-md bg-violet-50/30 px-3 py-2.5 flex flex-col gap-1.5">
      <div className="text-[10px] font-mono text-violet-700 uppercase tracking-wide">
        cross-document resolution
      </div>
      {questionText ? (
        <p className="text-sm text-ink dark:text-bright leading-snug italic">
          "{questionText}"
        </p>
      ) : (
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight italic">
          (question text not captured — id: {shortenId(p.question_id)})
        </p>
      )}
      <div className="text-[11px] font-mono text-ink dark:text-bright flex items-center gap-1.5 flex-wrap">
        <span className="px-1.5 py-0.5 rounded bg-ice-3 dark:bg-charcoal-1" title={p.question_document_id}>
          {shortenDocId(p.question_document_id)}
        </span>
        <span className="text-violet-600">→</span>
        <span className="px-1.5 py-0.5 rounded bg-ice-3 dark:bg-charcoal-1" title={p.answer_document_id}>
          {shortenDocId(p.answer_document_id)}
        </span>
      </div>
      <div className="text-[10px] font-mono text-shadow-1 dark:text-moonlight pt-0.5 flex items-center gap-1.5">
        <span>bridged by:</span>
        <button
          onClick={() => onCiteJump?.(p.answer_note_id)}
          className="text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 dark:bg-charcoal-1 px-1.5 py-0.5 rounded transition-colors"
          title={`jump to note ${p.answer_note_id}`}
        >
          ↩ {shortenId(p.answer_note_id)}
        </button>
      </div>
    </li>
  );
}

function shortenId(id: string): string {
  return id.length > 14 ? id.slice(0, 14) + "…" : id;
}

function shortenDocId(id: string): string {
  return id.length > 12 ? id.slice(0, 12) + "…" : id;
}
