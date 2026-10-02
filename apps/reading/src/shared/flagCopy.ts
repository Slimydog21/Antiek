/**
 * flagCopy — the one place the diligence surfaces read their shared
 * constants from (the note cap mirrors substrate/diligence/schema.py's
 * CHECK; the kind labels keep raw graph vocabulary out of the copy).
 */
export const NOTE_MAX_CHARS = 280;

export const KIND_LABELS: Record<string, string> = {
  concept: "concept",
  open_question: "open question",
  insight: "insight",
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}
