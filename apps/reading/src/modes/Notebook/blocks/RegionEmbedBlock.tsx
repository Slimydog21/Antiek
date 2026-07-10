import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { useEffect, useRef, useState } from "react";
import { stringAttr, intAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";
import { getHtmlProjectionByDocument, type HtmlProjectionAnchorMapping } from "../../../api/htmlProjections";
import { openReader } from "../../../workspace/actions";

const CANONICAL_ANCHOR_ID = /^antiek-anchor-[0-9a-f]{64}$/;

/**
 * Resolve the compatibility-only PDF page locator. Page locators are not
 * stable enough to open directly: only an unambiguous projection mapping is
 * accepted.
 */
export function resolveLegacyPageAnchor(
  mappings: readonly HtmlProjectionAnchorMapping[],
  page: number,
): string | null {
  const matches = mappings.filter(
    (mapping) =>
      mapping.state === "resolved" &&
      mapping.source_locator.kind === "pdf_page_bbox" &&
      mapping.source_locator.page === page,
  );
  return matches.length === 1 ? matches[0].html_anchor_id : null;
}

export function RegionEmbedNodeView({ node, deleteNode }: NodeViewProps) {
  const documentId = (node.attrs.document_id as string | null) ?? null;
  const anchorId = (node.attrs.anchor_id as string | null) ?? null;
  const sourcePage = (node.attrs.source_page as number | null) ?? null;
  const page = (node.attrs.page as number | null) ?? null;
  const caption = (node.attrs.caption as string | null) ?? null;
  const validAnchorId = anchorId && CANONICAL_ANCHOR_ID.test(anchorId) ? anchorId : null;
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setResolving(false);
    setError(null);
    return () => requestRef.current?.abort();
  }, [documentId, anchorId, page]);

  const open = () => {
    setError(null);
    if (!documentId) {
      setError("This region has no document and cannot be opened.");
      return;
    }
    if (validAnchorId) {
      openReader({ documentId, anchorId: validAnchorId });
      return;
    }
    if (anchorId) {
      setError("This region has a malformed canonical anchor and cannot be opened.");
      return;
    }
    if (page == null) {
      setError("This region has no anchor or legacy page locator and cannot be opened.");
      return;
    }

    const controller = new AbortController();
    requestRef.current?.abort();
    requestRef.current = controller;
    setResolving(true);
    void getHtmlProjectionByDocument(documentId, controller.signal).then(
      (projection) => {
        if (controller.signal.aborted) return;
        const resolvedAnchor = resolveLegacyPageAnchor(projection.anchor_mappings, page);
        if (!resolvedAnchor) {
          setError(`Legacy page ${page} does not resolve to exactly one region anchor.`);
          return;
        }
        openReader({ documentId, anchorId: resolvedAnchor });
      },
      (reason: unknown) => {
        if (controller.signal.aborted) return;
        const detail = reason instanceof Error && reason.message ? `: ${reason.message}` : "";
        setError(`Could not resolve legacy page ${page}${detail}`);
      },
    ).finally(() => {
      if (!controller.signal.aborted && requestRef.current === controller) setResolving(false);
    });
  };

  const displayPage = sourcePage ?? page;
  const canAttemptOpen = Boolean(documentId && (validAnchorId || page != null));
  const unavailable = !documentId
    ? "This region has no document and cannot be opened."
    : anchorId && !validAnchorId
      ? "This region has a malformed canonical anchor and cannot be opened."
      : !validAnchorId && page == null
      ? "This region has no anchor or legacy page locator and cannot be opened."
      : null;

  return (
    <NodeViewWrapper className="my-3" data-block="region-embed">
      <LemonCard
        elevation="z1"
        colour="glacial"
        title={
          <span className="flex items-center justify-between">
            <span>
              Region · {documentId ? documentId.slice(0, 12) : "(no document)"}
              {displayPage != null ? ` · p.${displayPage}` : ""}
            </span>
            <span className="font-sans normal-case tracking-normal flex gap-2">
              <button
                type="button"
                onClick={open}
                disabled={!canAttemptOpen || resolving}
                className="text-[11px] text-sun-deep dark:text-sun hover:underline disabled:opacity-50 disabled:no-underline"
              >
                {resolving ? "Resolving…" : "Open region"}
              </button>
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
        {error && <p role="alert" className="mb-2 font-mono text-[12px] text-red-700">{error}</p>}
        {!error && unavailable && <p role="status" className="mb-2 font-mono text-[12px] text-ink-mute">{unavailable}</p>}
        {caption ? (
          <p className="font-serif italic text-[14px] text-ink-soft dark:text-starlight">
            "{caption}"
          </p>
        ) : (
          <p className="font-mono text-[12px] text-ink-mute dark:text-moonlight italic">
            no caption · open the source to recapture the region
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
      anchor_id: stringAttr("anchor_id"),
      source_page: intAttr("source_page"),
      // Read-only compatibility for notebook HTML written before SPR-03.
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
