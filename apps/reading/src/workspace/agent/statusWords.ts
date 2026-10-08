/**
 * statusWords.ts — one Antiek-authored status word per turn (SPR-07 M3,
 * refs pattern 15). THE MECHANISM IS TURN-INDEX DETERMINISM: the word is
 * STATUS_WORDS[turnIndex % 5], nothing random, so a test pins the word a
 * turn shows by its index. There is no test flag and none is needed — the
 * sprint page's "deterministic under a test flag" names the guarantee, not
 * the mechanism (critic note at 900fd429a; SEAMS.md §3).
 */
export const STATUS_WORDS = ["reading", "weighing", "drafting", "checking", "answering"] as const;
export type StatusWord = (typeof STATUS_WORDS)[number];

export function statusWordFor(turnIndex: number): StatusWord {
  return STATUS_WORDS[((turnIndex % STATUS_WORDS.length) + STATUS_WORDS.length) % STATUS_WORDS.length];
}

export type TurnStatus = "pending" | "streaming" | "done" | "failed";

/** Present tense while the turn runs; past tense once it settled. */
export function statusLabel(status: TurnStatus, turnIndex: number): string {
  if (status === "done") return "answered";
  if (status === "failed") return "couldn't answer";
  return statusWordFor(turnIndex);
}
