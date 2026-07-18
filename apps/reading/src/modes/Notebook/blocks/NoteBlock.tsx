import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";

import { stringAttr } from "./attrHelpers";

import { emitWernerExperience } from "../../../werner/reactionBus";
/** Inline note block — a single note from the operator or the agent. */
function NoteNodeView({ node, deleteNode }: NodeViewProps) {
  const text = (node.attrs.text as string | null) ?? "";
  return (
    <NodeViewWrapper className="my-2" data-block="note">
      <div className="border-l-edge border-sun bg-sun/10 pl-3 py-2 pr-4 rounded-r flex items-start gap-2">
        <span className="text-ink dark:text-sun font-mono text-[10px] font-bold uppercase tracking-wider shrink-0 mt-1">
          note
        </span>
        <p className="flex-1 font-serif text-[15px] leading-relaxed text-ink dark:text-bright">
          {text || (
            <span className="italic text-ink-mute dark:text-moonlight">
              (empty note — edit attributes via the substrate)
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
          aria-label="Remove note"
          className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor leading-none mt-1"
        >
          ✕
        </button>
      </div>
    </NodeViewWrapper>
  );
}

export const NoteBlock = Node.create({
  name: "noteBlock",
  group: "block",
  atom: true,
  draggable: true,
  // Explicit parseHTML/renderHTML per attribute. AI-tool-call
  // dispatched <antiek-note text="…"> round-trips losslessly.
  addAttributes() {
    return {
      note_id: stringAttr("note_id"),
      text: stringAttr("text"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-note" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-note", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(NoteNodeView);
  },
});

export default NoteBlock;
