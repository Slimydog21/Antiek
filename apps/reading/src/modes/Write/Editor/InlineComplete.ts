/**
 * Tab (paragraph) / Mod-j inline autocomplete for the Write editor (CK-3).
 *
 * Trigger: Tab when the selection is collapsed inside a paragraph — list Tab
 * indent is left to StarterKit (we return false outside paragraph). Mod-j is
 * the same affordance without the paragraph-only guard.
 */

import { Extension } from "@tiptap/core";
import type { Editor } from "@tiptap/react";
import type { EditorState } from "@tiptap/pm/state";

import { completeInline } from "../../../lib/api";

/** Max plain-text context shipped to POST /complete (backend allows 8000). */
export const INLINE_COMPLETE_CONTEXT_CAP = 4000;

export interface InlineCompleteStorage {
  pending: boolean;
}

/** Plain text from the start of the current textblock up to the cursor. */
export function extractBlockPrefix(state: EditorState): string {
  const { $from, empty } = state.selection;
  if (!empty) return "";
  const parent = $from.parent;
  if (!parent.isTextblock) return "";
  const blockStart = $from.start();
  return state.doc.textBetween(blockStart, $from.pos, "", "");
}

/** Whether a completion request should be sent (prefix + not already in flight). */
export function shouldRequestCompletion(prefix: string, pending: boolean): boolean {
  if (pending) return false;
  return prefix.trim().length > 0;
}

export function capDocumentContext(fullText: string, max = INLINE_COMPLETE_CONTEXT_CAP): string {
  return fullText.slice(0, max);
}

type CompleteFn = typeof completeInline;

export async function runInlineComplete(
  editor: Editor,
  storage: InlineCompleteStorage,
  complete: CompleteFn = completeInline,
): Promise<void> {
  const prefix = extractBlockPrefix(editor.state);
  if (!shouldRequestCompletion(prefix, storage.pending)) return;

  storage.pending = true;
  try {
    const document_context = capDocumentContext(editor.getText());
    const res = await complete({
      prefix,
      document_context: document_context || undefined,
    });
    if (res.text) {
      editor.commands.insertContent(res.text);
    }
  } catch {
    // Best-effort — a failed completion must not interrupt the writer.
  } finally {
    storage.pending = false;
  }
}

function tryTrigger(editor: Editor, storage: InlineCompleteStorage): boolean {
  const prefix = extractBlockPrefix(editor.state);
  if (!shouldRequestCompletion(prefix, storage.pending)) return false;
  void runInlineComplete(editor, storage);
  return true;
}

export const InlineComplete = Extension.create<Record<string, never>, InlineCompleteStorage>({
  name: "inlineComplete",

  addStorage() {
    return { pending: false };
  },

  addKeyboardShortcuts() {
    return {
      Tab: () => {
        const { editor } = this;
        if (!editor.isActive("paragraph")) return false;
        if (!editor.state.selection.empty) return false;
        return tryTrigger(editor, this.storage);
      },
      "Mod-j": () => {
        const { editor } = this;
        if (!editor.state.selection.empty) return false;
        return tryTrigger(editor, this.storage);
      },
    };
  },
});