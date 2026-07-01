import { regionOfSelection } from "./floatMenuActions";
import type { FloatMenuSelection } from "./useFloatMenuSelection";

/** One completed turn in the FloatMenu Dialogue panel (session-local). */
export interface StoredDialogueTurn {
  question: string;
  answer: string;
}

export interface StoredDialogueSession {
  turns: StoredDialogueTurn[];
  threadNodeId: string | null;
}

/** Stable key for the passage anchor (matches backend re-attach semantics). */
export function dialogueSessionKey(
  investigationId: string,
  selection: FloatMenuSelection,
): string {
  const region = regionOfSelection(selection);
  const anchor = region
    ? [
        region.document_id,
        region.block_id,
        region.char_start ?? "-",
        region.char_end ?? "-",
      ].join("|")
    : `free:${selection.text.slice(0, 120)}`;
  return `antiek:dialogue:${investigationId}:${anchor}`;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function isStoredDialogueTurn(value: unknown): value is StoredDialogueTurn {
  const turn = record(value);
  return (
    turn !== null &&
    typeof turn.question === "string" &&
    typeof turn.answer === "string"
  );
}

function isStoredDialogueSession(value: unknown): value is StoredDialogueSession {
  const session = record(value);
  return (
    session !== null &&
    Array.isArray(session.turns) &&
    session.turns.every(isStoredDialogueTurn) &&
    (session.threadNodeId === undefined ||
      session.threadNodeId === null ||
      typeof session.threadNodeId === "string")
  );
}

export function loadDialogueSession(key: string): StoredDialogueSession | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!isStoredDialogueSession(parsed)) return null;
    return {
      turns: parsed.turns,
      threadNodeId: parsed.threadNodeId ?? null,
    };
  } catch {
    return null;
  }
}

export function saveDialogueSession(key: string, session: StoredDialogueSession): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(session));
  } catch {
    // Quota / private mode — conversation stays in-memory for this mount only.
  }
}
