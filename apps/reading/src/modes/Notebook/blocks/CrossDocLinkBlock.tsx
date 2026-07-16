import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";

import { emitWernerExperience } from "../../../werner/reactionBus";
/** Cross-document bridge — two source thumbnails + a bridge note. */
function CrossDocLinkNodeView({ node, deleteNode }: NodeViewProps) {
  const fromDoc = (node.attrs.from_doc as string | null) ?? "(unset)";
  const toDoc = (node.attrs.to_doc as string | null) ?? "(unset)";
  const bridge = (node.attrs.bridge as string | null) ?? null;
  return (
    <NodeViewWrapper className="my-3" data-block="cross-doc-link">
      <LemonCard
        elevation="z1"
        title={
          <span className="flex items-center justify-between">
            <span>
              Cross-doc · {fromDoc.slice(0, 10)} ↔ {toDoc.slice(0, 10)}
            </span>
            <button
              type="button"
              onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
              aria-label="Remove block"
              className="font-sans normal-case tracking-normal text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
            >
              ✕
            </button>
          </span>
        }
      >
        <p className="font-serif text-[14px] leading-relaxed text-ink-soft dark:text-starlight">
          {bridge || (
            <span className="italic text-ink-mute dark:text-moonlight">
              (no bridge note)
            </span>
          )}
        </p>
      </LemonCard>
    </NodeViewWrapper>
  );
}

export const CrossDocLinkBlock = Node.create({
  name: "crossDocLink",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      bridge_id: stringAttr("bridge_id"),
      from_doc: stringAttr("from_doc"),
      to_doc: stringAttr("to_doc"),
      bridge: stringAttr("bridge"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-cross-doc-link" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-cross-doc-link", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(CrossDocLinkNodeView);
  },
});

export default CrossDocLinkBlock;
