import type { ParkedQuestionEntry } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

interface Props {
  questions: ParkedQuestionEntry[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  onSelect: (q: ParkedQuestionEntry) => void;
}

/**
 * Watch-for-later folder UI on top of `question.identified` events
 * filtered by an "unsharpened" state — questions identified during
 * note-taking that have NOT yet been escalated to a child
 * investigation or resolved by a document.
 *
 * Per master-spec §2.6 (curiosity-capture primitive) + §4.5
 * (Brainstorming Workstation surface).
 */
export default function WatchForLaterFolder({
  questions,
  loading,
  error,
  selectedId,
  onSelect,
}: Props) {
  if (loading) {
    return (
      <div className="p-4 text-xs text-shadow-1 dark:text-moonlight italic">
        Loading parked questions…
      </div>
    );
  }
  if (error) {
    return (
      <div className="p-4 text-xs text-emperor">
        Couldn't load the folder: {error}
      </div>
    );
  }
  if (questions.length === 0) {
    return (
      <div className="p-4 text-xs text-shadow-1 dark:text-moonlight italic leading-relaxed">
        Empty. Open questions from your investigations and document
        wrestling sessions will park themselves here automatically.
      </div>
    );
  }

  return (
    <div className="py-2">
      <div className="px-4 py-2 text-xs font-semibold text-ink dark:text-bright uppercase tracking-wide">
        Watch for later
      </div>
      <ul className="space-y-px">
        {questions.map((q) => {
          const isSelected = q.question_id === selectedId;
          return (
            <li key={q.question_id}>
              <button
                type="button"
                onClick={() => {
                  // Living-TV: selecting a parked question is a curious glance.
                  emitWernerExperience("highlight");
                  onSelect(q);
                }}
                className={`w-full text-left px-4 py-2 transition-colors ${
                  isSelected
                    ? "bg-ice-0 dark:bg-charcoal-2 shadow-sm border-l-2 border-ink dark:border-bright"
                    : "hover:bg-ice-3 dark:bg-charcoal-1 border-l-2 border-transparent"
                }`}
              >
                <p className="text-sm text-ink dark:text-bright leading-snug font-serif">
                  {q.question_text || (
                    <em className="text-shadow-1 dark:text-moonlight">(no text)</em>
                  )}
                </p>
                <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight font-mono">
                  {relativeTime(q.parked_at)} ·{" "}
                  <span className="text-ink-mute dark:text-moonlight">
                    {q.source_investigation_id}
                  </span>
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function relativeTime(iso: string): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}
