import type { ParkedQuestionEntry } from "../../lib/api";

interface Props {
  question: ParkedQuestionEntry;
  launching: boolean;
  onLaunch: () => void;
}

/**
 * Selected parked-question detail pane. Shows the question text +
 * source context + launch affordance.
 *
 * Launch button posts to /watch-for-later/{question_id}/launch which
 * spawns a child investigation seeded by the parked question text and
 * emits a question.escalated_to_research event tying parent → child.
 * The folder hides the question on next refresh because it is now
 * sharpened.
 *
 * Per master-spec §4.5 Brainstorming Workstation components.
 */
export default function ParkedQuestion({
  question,
  launching,
  onLaunch,
}: Props) {
  return (
    <div className="max-w-2xl mx-auto px-8 py-10 space-y-6">
      <section>
        <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-3">
          Parked question
        </h2>
        <p className="text-xl font-serif text-stone-900 leading-relaxed">
          {question.question_text || (
            <em className="text-stone-500">(no text)</em>
          )}
        </p>
      </section>

      <section className="space-y-2">
        <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide">
          Context
        </h3>
        <dl className="text-sm text-stone-700 space-y-1 font-mono">
          <Row k="question_id" v={question.question_id} />
          <Row
            k="source investigation"
            v={question.source_investigation_id}
          />
          {question.source_document_id && (
            <Row k="source document" v={question.source_document_id} />
          )}
          {question.anchor_region_id && (
            <Row k="anchor region" v={question.anchor_region_id} />
          )}
          <Row k="parked at" v={question.parked_at} />
        </dl>
      </section>

      <section className="pt-2">
        <button
          type="button"
          onClick={onLaunch}
          disabled={launching}
          className="px-4 py-2 rounded-md bg-stone-900 text-white text-sm font-medium hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {launching ? "Launching…" : "Launch investigation"}
        </button>
        <p className="mt-2 text-xs text-stone-500 leading-relaxed">
          Spawns a child investigation seeded by this question and
          marks it sharpened in the source trajectory. You'll be
          taken to the new investigation in the Research Workstation.
        </p>
      </section>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="text-stone-500 shrink-0 w-40">{k}</dt>
      <dd className="text-stone-900 break-all">{v}</dd>
    </div>
  );
}
