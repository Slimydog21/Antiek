import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr, intAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";
import { openPdfPanel } from "../../../workspace/actions";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Region-embed block — references a PDF region by document_id + page.
 * Renders a placeholder card with an "Open at page" affordance that
 * opens the PdfViewer as a floating panel jumped to the page.
 */
function RegionEmbedNodeView({ node, deleteNode }: NodeViewProps) {
  const documentId = (node.attrs.document_id as string | null) ?? null;
  const page = (node.attrs.page as number | null) ?? null;
  const caption = (node.attrs.caption as string | null) ?? null;

  return (
    <NodeViewWrapper className="my-3" data-block="region-embed">
      <LemonCard
        elevation="z1"
        colour="glacial"
        title={
          <span className="flex items-center justify-between">
            <span>
              Region · {documentId ? documentId.slice(0, 12) : "(no document)"}
              {page ? ` · p.${page}` : ""}
            </span>
            <span className="font-sans normal-case tracking-normal flex gap-2">
              {documentId && (
                <button
                  type="button"
                  onClick={() => openPdfPanel({ documentId, page: page ?? undefined })}
                  className="text-[11px] text-sun-deep dark:text-sun hover:underline"
                >
                  Open at page
                </button>
              )}
              <button
                type="button"
                onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
                aria-label="Remove block"
                className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
              >
                ✕
              </button>
            </span>
          </span>
        }
      >
        {caption ? (
          <p className="font-serif italic text-[14px] text-ink-soft dark:text-starlight">
            "{caption}"
          </p>
        ) : (
          <p className="font-mono text-[12px] text-ink-mute dark:text-moonlight italic">
            no caption · open the PDF to recapture the region
          </p>
        )}
      </LemonCard>
    </NodeViewWrapper>
  );
}

export const RegionEmbedBlock = Node.create({
  name: "regionEmbed",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      document_id: stringAttr("document_id"),
      page: intAttr("page"),
      caption: stringAttr("caption"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-region-embed" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-region-embed", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(RegionEmbedNodeView);
  },
});

export default RegionEmbedBlock;
