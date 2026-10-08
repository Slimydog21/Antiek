/**
 * composerKeys.ts — the composer's pure key contract (SPR-07 M2; refs
 * pattern 9), the Escape ladder (pattern 10) and the canned-prompt digit
 * rule (M7, fix 6). Pure functions: the component maps events onto them
 * and performs the side effects.
 */
export type ComposerKeyAction = "complete" | "move-up" | "move-down" | "dismiss" | "send" | "newline" | "none";

export interface ComposerKeyInput {
  key: string;
  shift: boolean;
  /** KeyboardEvent.isComposing: an IME is assembling a character; Enter commits it, never sends. */
  isComposing: boolean;
  pickerOpen: boolean;
  optionCount: number;
  /** -1 when nothing is highlighted. */
  highlighted: number;
}

export interface ComposerKeyResult {
  action: ComposerKeyAction;
  /** For move-up/move-down: the next highlighted index (wraps). */
  highlighted?: number;
}

export function resolveComposerKey(i: ComposerKeyInput): ComposerKeyResult {
  if (i.isComposing) return { action: "none" };
  if (i.pickerOpen && i.optionCount > 0) {
    if (i.key === "ArrowDown") return { action: "move-down", highlighted: (i.highlighted + 1) % i.optionCount };
    if (i.key === "ArrowUp") return { action: "move-up", highlighted: (i.highlighted - 1 + i.optionCount) % i.optionCount };
    if (i.key === "Enter" || i.key === "Tab") return { action: "complete" };
    if (i.key === "Escape") return { action: "dismiss" };
  }
  if (i.key === "Enter") return { action: i.shift ? "newline" : "send" };
  return { action: "none" };
}

export const ESCAPE_LADDER = ["picker", "recording", "chip", "blur", "close"] as const;
export type EscapeRung = (typeof ESCAPE_LADDER)[number];

/** One Escape, one rung: the first that applies. "recording" is a stub
 *  rung until a mic exists; "blur" moves focus to the pane root; "close"
 *  is the root's own key. */
export function nextEscapeRung(i: { pickerOpen: boolean; recording: boolean; hasChip: boolean; composerFocused: boolean }): EscapeRung {
  if (i.pickerOpen) return "picker";
  if (i.recording) return "recording";
  if (i.hasChip) return "chip";
  if (i.composerFocused) return "blur";
  return "close";
}

/** 1/2/3 pick a canned prompt ONLY when both the thread and the draft are
 *  empty and the draft was never touched (fix 6): a user who typed and
 *  deleted is typing, and a digit is a digit. */
export function cannedPromptForDigit(key: string, i: { threadEmpty: boolean; draftEmpty: boolean; modified: boolean }): 1 | 2 | 3 | null {
  if (!i.threadEmpty || !i.draftEmpty || i.modified) return null;
  if (key === "1") return 1;
  if (key === "2") return 2;
  if (key === "3") return 3;
  return null;
}
