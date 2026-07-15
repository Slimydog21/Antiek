import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useCallback, useEffect, useRef } from "react";

import { postTypedEvent } from "../../../lib/api";
import type { TypedPayload } from "../../../generated/types";
import { Citation } from "./Citation";
import { LegoBlock } from "./BlockNode";
import { diffBlocks, toEditCapturedPayload } from "./editCapture";
import type { EditorBlock } from "./locator";
import { newBlockId } from "./locator";
import { InlineComplete } from "./InlineComplete";
import { BlockId, docToBlocks } from "./tiptapAdapter";

/**
 * The Write structured block editor (specs/write/ SPR-04).
 *
 * Replaces CreationStudio's plain `<textarea>` ProseEditor with a TipTap
 * block/tree editor: lego blocks (provenance-bearing) + prose, inline
 * citations, and — the point of Write — **granular edit capture**. Every
 * edit is diffed into a structured before/after pair and emitted as an
 * `edit.captured` event (SPR-02 schema) via `postTypedEvent`. Undo/redo is
 * coordinated so reverted edits are flagged and excluded from training
 * signal.
 *
 * Editor-choice rationale (rigor #1, a long-lived commitment): TipTap.
 * It is already the house editor (the Notebook mode is built on it) and a
 * declared dependency, so the choice adds no new surface and inherits the
 * Notebook's custom-node + attr-round-trip conventions. What would reverse
 * it: a need for true tree-structured (nested) block editing that
 * ProseMirror's flat-block model fights — at which point Lexical's nested
 * node model would be reconsidered. Not today.
 *
 * Note: this React glue is type-checked (tsc) but its live behavior needs
 * a browser; the diff + revert + locator cores are unit-tested
 * (editCapture.test.ts / locator.test.ts), which is where the data-flywheel
 * correctness actually lives.
 */
export interface WriteEditorProps {
  deliverableId: string;
  sectionId: string;
  /** TipTap JSON or HTML for the section's current content. */
  initialContent?: string;
  /** Opaque editing-session id so multi-session trajectories stitch. */
  sessionId?: string;
  investigationId?: string;
  placeholder?: string;
  className?: string;
  /** Fires the editor's plain text on every update — lets a host (e.g.
   * CreationStudio) keep persisting coarse prose_text via the existing
   * save path while the granular edit.captured stream flows underneath. */
  onContentChange?: (plainText: string) => void;
}

export function WriteEditor({
  deliverableId,
  sectionId,
  initialContent,
  sessionId,
  investigationId = "__operator__",
  placeholder = "Write here. Drag lego blocks in from the repository, or generate a first draft.",
  className,
  onContentChange,
}: WriteEditorProps) {
  // Snapshot of the section's blocks after the last captured update.
  const prevBlocks = useRef<EditorBlock[]>([]);
  // Set true for the single update produced by an undo/redo so the diff
  // flags reverted edits (coordination point — reverts are not signal).
  const nextUpdateIsRevert = useRef<boolean>(false);
  const session = useRef<string>(sessionId ?? newBlockId());

  const emitEdits = useCallback(
    (next: EditorBlock[], isUndo: boolean) => {
      const edits = diffBlocks(sectionId, prevBlocks.current, next, { isUndo });
      for (const edit of edits) {
        const outlineBlockId =
          next.find((b) => b.blockId === edit.locator.blockId)?.outlineBlockId ?? null;
        const payload = toEditCapturedPayload(
          deliverableId, edit, session.current, outlineBlockId,
        );
        // The payload is the generated EditCapturedPayload variant.
        void postTypedEvent({
          investigation_id: investigationId,
          payload: payload as unknown as TypedPayload,
          role: "write_editor",
        }).catch(() => {
          // Capture is best-effort telemetry; a failed POST must never
          // interrupt the writer's flow. (A retry/queue lands when the
          // edit-ingest endpoint is hardened — see handoff.)
        });
      }
      prevBlocks.current = next;
    },
    [deliverableId, sectionId, investigationId],
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      BlockId,
      Citation,
      LegoBlock,
      Placeholder.configure({ placeholder }),
      InlineComplete,
    ],
    content: initialContent ?? "",
    onCreate: ({ editor: ed }) => {
      prevBlocks.current = docToBlocks(ed.getJSON());
    },
    onUpdate: ({ editor: ed }) => {
      const isUndo = nextUpdateIsRevert.current;
      nextUpdateIsRevert.current = false;
      emitEdits(docToBlocks(ed.getJSON()), isUndo);
      onContentChange?.(ed.getText());
    },
  });

  useEffect(() => {
    if (!editor || initialContent === undefined || editor.getHTML() === initialContent) return;
    editor.commands.setContent(initialContent, { emitUpdate: false });
    prevBlocks.current = docToBlocks(editor.getJSON());
  }, [editor, initialContent]);

  // Detect undo/redo at the keyboard layer so the next onUpdate is flagged
  // reverted. (ProseMirror's history plugin does not surface "this update
  // was an undo" in onUpdate; the keyboard signal is the reliable hook.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "z") {
        nextUpdateIsRevert.current = true;
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  return <EditorContent editor={editor} className={className} />;
}

export default WriteEditor;
