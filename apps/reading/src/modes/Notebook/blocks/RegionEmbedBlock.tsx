import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr, intAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";
import { useOpenDocument } from "../../../lib/openDocument";

/**
 * Region-embed block — references a PDF region by document_id + page.
 * Renders a placeholder card with an "Open at page" affordance that opens
 * the referenced document in the ONE Reader (SPR-05 — was a bespoke
 * `openPdfPanel` floating pdf.js panel, a second open-a-document fork; now
 * routes through `openDocument` → the gated /read/:id route like every other
 * door). The `page` attr is a 1-based page LABEL; the reader's `page` opt is a
 * 0-based index, so we convert it the same way ChunkModal does
 * (`Math.max(0, n-1)`).
 */
function RegionEmbedNodeView({ node, deleteNode }: NodeViewProps) {
  const openDocument = useOpenDocument();
  const documentId = (node.attrs.document_id as string | null) ?? null;
  const page = (node.attrs.page as number | null) ?? null;
  const caption = (node.attrs.caption as string | null) ?? null;
  // The `page` attr is a 1-based page label (the "p.N" the card shows);
  // openDocument's `page` opt is a 0-based reader index. Convert honestly
  // (N → N-1, clamped at 0) — the SAME conversion ChunkModal applies.
  const readerPage = page !== null ? Math.max(0, page - 1) : undefined;

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
                  onClick={() => openDocument(documentId, { page: readerPage })}
                  className="text-[11px] text-sun-deep dark:text-sun hover:underline"
                >
                  Open at page
                </button>
              )}
              <button
                type="button"
                onClick={() => deleteNode()}
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
