import type { ParkedQuestionEntry } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

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
        <h2 className="text-xs font-semibold text-shadow-1 dark:text-moonlight uppercase tracking-wide mb-3">
          Parked question
        </h2>
        <p className="text-xl font-serif text-ink dark:text-bright leading-relaxed">
          {question.question_text || (
            <em className="text-shadow-1 dark:text-moonlight">(no text)</em>
          )}
        </p>
      </section>

      <section className="space-y-2">
        <h3 className="text-xs font-semibold text-shadow-1 dark:text-moonlight uppercase tracking-wide">
          Context
        </h3>
        <dl className="text-sm text-ink dark:text-bright space-y-1 font-mono">
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
          onClick={() => {
            // Living-TV: launching a parked question is a deep-research start.
            emitWernerExperience("deep_research_start");
            onLaunch();
          }}
          disabled={launching}
          className="px-4 py-2 rounded-md bg-ink text-white text-sm font-medium hover:bg-shadow-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {launching ? "Launching…" : "Launch investigation"}
        </button>
        <p className="mt-2 text-xs text-shadow-1 dark:text-moonlight leading-relaxed">
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
      <dt className="text-shadow-1 dark:text-moonlight shrink-0 w-40">{k}</dt>
      <dd className="text-ink dark:text-bright break-all">{v}</dd>
    </div>
  );
}
