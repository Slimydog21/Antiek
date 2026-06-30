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

export function loadDialogueSession(key: string): StoredDialogueSession | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredDialogueSession;
    if (!Array.isArray(parsed.turns)) return null;
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