import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Image block — inline image with caption. Source resolves via the
 * substrate attachments endpoint in the full backend; on main, the
 * src can be a direct URL or a data URI for the operator's drag-
 * dropped images.
 */
function ImageNodeView({ node, deleteNode }: NodeViewProps) {
  const src = (node.attrs.src as string | null) ?? null;
  const alt = (node.attrs.alt as string | null) ?? "";
  const caption = (node.attrs.caption as string | null) ?? "";
  return (
    <NodeViewWrapper className="my-3" data-block="image">
      <figure className="border-edge border-sun bg-ice-0 dark:bg-charcoal-2 rounded-hog shadow-z1 dark:shadow-z1-night overflow-hidden relative">
        {/* S7 WP-7.3 acceptance: "open as panel" affordance.
            For an image, open the src in a lightbox floating panel
            sized to its natural dimensions (capped by the viewport
            via PdfViewer's clampRectToViewport in PanelHandle). */}
        {src && (
          <button
            type="button"
            onClick={() => {
              import("../../../workspace/WorkspaceStore").then(
                ({ useWorkspace }) => {
                  useWorkspace.getState().open(
                    "Lightbox",
                    { src, alt, caption },
                    {
                      mode: "floating",
                      title: "Image · lightbox",
                      id: `lightbox:${src.slice(0, 32)}`,
                    },
                  );
                },
              );
            }}
            className="absolute top-2 right-10 text-[11px] text-ink dark:text-bright bg-ice-0 dark:bg-charcoal-2 border border-ink dark:border-bright rounded px-1.5 py-0.5 leading-none hover:bg-sun/15"
            title="Open in lightbox panel"
          >
            ↗
          </button>
        )}
        <button
          type="button"
          onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
          aria-label="Remove image"
          className="absolute top-2 right-2 text-[11px] text-ink dark:text-bright bg-ice-0 dark:bg-charcoal-2 border border-ink dark:border-bright rounded px-1.5 py-0.5 leading-none hover:text-emperor"
        >
          ✕
        </button>
        {src ? (
          <img
            src={src}
            alt={alt}
            className="block max-h-[480px] max-w-full mx-auto"
          />
        ) : (
          <div className="aspect-video flex items-center justify-center bg-ice-3 dark:bg-charcoal-1 text-ink-mute dark:text-moonlight font-mono text-[12px]">
            (no src — substrate-ref pending)
          </div>
        )}
        {caption && (
          <figcaption className="font-serif italic text-[13.5px] text-ink-soft dark:text-starlight px-4 py-2 border-t-edge border-sun">
            {caption}
          </figcaption>
        )}
      </figure>
    </NodeViewWrapper>
  );
}

export const ImageBlock = Node.create({
  name: "imageBlock",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      src: stringAttr("src"),
      alt: stringAttr("alt"),
      caption: stringAttr("caption"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-image" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-image", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(ImageNodeView);
  },
});

export default ImageBlock;
