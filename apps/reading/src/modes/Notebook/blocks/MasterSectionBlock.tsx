import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Master-section block — embeds a synthesis fragment (a section of
 * MASTER.md) inline in the notebook. Substrate-ref by synthesis id +
 * section heading. Render-time fetch in the full backend; main shows
 * the ref + a placeholder.
 */
function MasterSectionNodeView({ node, deleteNode }: NodeViewProps) {
  const synthesisId = (node.attrs.synthesis_id as string | null) ?? "(unset)";
  const section = (node.attrs.section as string | null) ?? "";
  return (
    <NodeViewWrapper className="my-3" data-block="master-section">
      <div className="border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2 shadow-z1 dark:shadow-z1-night p-4 relative">
        <header className="flex items-center justify-between mb-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft dark:text-moonlight">
            Synthesis · {synthesisId.slice(0, 12)}
            {section ? ` · ${section}` : ""}
          </span>
          <button
            type="button"
            onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
            aria-label="Remove block"
            className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
          >
            ✕
          </button>
        </header>
        <p className="font-serif text-[15px] leading-relaxed text-ink dark:text-bright">
          (synthesis fragment rendered here in the full backend; the
          substrate stores the ref + the renderer pulls fresh content
          at render time per architecture_notes §13)
        </p>
      </div>
    </NodeViewWrapper>
  );
}

export const MasterSectionBlock = Node.create({
  name: "masterSection",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      synthesis_id: stringAttr("synthesis_id"),
      section: stringAttr("section"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-master-section" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-master-section", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(MasterSectionNodeView);
  },
});

export default MasterSectionBlock;
