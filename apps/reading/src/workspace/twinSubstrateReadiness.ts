/**
 * Residual (arq): pure readiness for the recursive twin note-taker substrate.
 *
 * Every information asset should carry twin insights + questions (LLM as
 * perfect note-taker). This helper reports honest readiness without inventing
 * notes — empty counts stay empty.
 *
 * substrate_ready = at least one insight AND one question (both legs of the twin).
 */

export type TwinSubstrateReadiness = {
  note_count: number;
  insight_count: number;
  question_count: number;
  other_count: number;
  has_insights: boolean;
  has_questions: boolean;
  /** True when both insight and question substrate legs are present. */
  substrate_ready: boolean;
  empty: boolean;
  /** Short operator-facing summary (no invented readiness). */
  summary: string;
};

function nonNegInt(n: number | null | undefined): number {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

/**
 * Compute twin substrate readiness from counts and/or note kind list.
 * When notes are provided, kinds are counted; explicit counts override when
 * larger than derived (server aggregate honesty).
 */
export function twinSubstrateReadiness(opts: {
  insight_count?: number | null;
  question_count?: number | null;
  note_count?: number | null;
  notes?: readonly { kind?: string | null }[] | null;
}): TwinSubstrateReadiness {
  let insights = 0;
  let questions = 0;
  let other = 0;
  const notes = opts.notes || [];
  for (const n of notes) {
    const k = String(n?.kind || "")
      .trim()
      .toLowerCase();
    if (k === "insight") insights += 1;
    else if (k === "question") questions += 1;
    else if (k) other += 1;
  }
  const insight_count = Math.max(insights, nonNegInt(opts.insight_count));
  const question_count = Math.max(questions, nonNegInt(opts.question_count));
  const other_count = other;
  const fromNotes = notes.length;
  const note_count = Math.max(
    fromNotes,
    nonNegInt(opts.note_count),
    insight_count + question_count + other_count,
  );
  const has_insights = insight_count > 0;
  const has_questions = question_count > 0;
  const empty = note_count === 0;
  const substrate_ready = has_insights && has_questions;

  let summary: string;
  if (empty) {
    summary = "empty twin substrate · seed offline notes to begin";
  } else if (substrate_ready) {
    summary = `substrate ready · insights=${insight_count} · questions=${question_count}`;
  } else if (has_insights && !has_questions) {
    summary = `insights only (${insight_count}) · missing questions leg`;
  } else if (has_questions && !has_insights) {
    summary = `questions only (${question_count}) · missing insights leg`;
  } else {
    summary = `${note_count} note(s) without insight/question kinds`;
  }

  return {
    note_count,
    insight_count,
    question_count,
    other_count,
    has_insights,
    has_questions,
    substrate_ready,
    empty,
    summary,
  };
}
