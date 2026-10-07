/**
 * statusWords.ts — one Antiek-authored status word per turn (SPR-07 M3,
 * refs pattern 15). Deterministic by turn index; nothing random, so a
 * test can pin the word a turn shows.
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
