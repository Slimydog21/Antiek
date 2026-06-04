import "katex/dist/katex.min.css";
import "./reader.css";

import { forwardRef, useMemo } from "react";

import type {
  Block,
  Document,
  TocEntry,
} from "../../types/document_model.gen";
import type { OpenDocument } from "../../lib/openDocument.contract";
import Blocks from "./blocks/Blocks";
import { ReaderProvider, useReaderContext } from "./ReaderContext";

/**
 * Reader — the ONE document renderer (SPR-03 M2/M3/M4/M5).
 *
 * Renders the SPR-01 typed-block `Document` with full typographic fidelity over
 * the Charter-serif register: every block type (heading 1–6, paragraph, list,
 * table with column alignment, code, KaTeX display math, figure, blockquote,
 * footnote) and every inline span (text/strong/emphasis/link/code/math and the
 * first-class clickable `citation`). It REPLACES the 24-line `renderBlocks`
 * flattener (`ReadingColumn.tsx:62`) that collapsed all headings to one <h2> and
 * dumped paragraphs as `whitespace-pre-wrap` — the diagnosed "plain html text"
 * root cause.
 *
 * What it KEEPS from the good register (the caller, BookReader, owns the page
 * chrome around it — TOC sidebar, day/night surface, capped measure, attribution,
 * voice notes, FloatMenu mount): this component is the BODY renderer those
 * compose around. It forwards a ref so the FloatMenu selection SCOPE (the
 * `<article>`) is preserved verbatim, and it stamps the SPR-07 attribution
 * markers (`data-akb-asset-id` / optional `data-akb-chunk-id`) exactly as the
 * old ReadingColumn did, so the per-second attribution layer is unbroken.
 *
 * Data contract (rigor #1, honesty): this is the RENDER component. It takes the
 * already-resolved typed `Document` as a prop. The GATED FETCH + mount
 * (`openDocument` → consult the §9.0 serve gate → fetch the model) is SPR-05's
 * job; this sprint stubs `openDocument` for citations. The caller (BookReader)
 * deserializes `structured_blocks` from the existing /full-text serve response
 * and passes the Document here; when `structured_blocks` is NULL (a legacy /
 * un-backfilled doc), the caller falls back to the legacy `raw_text` flattener —
 * additive, never a blank.
 */

export interface ReaderProps {
  /** The resolved typed-block document (the SPR-01 model). */
  document: Document;
  /** The §9.0 asset id for SPR-07 attribution — pass the document id ONLY when
   *  the gate served the FULL body (a servable asset); null/omit for a gated
   *  preview so the sampler never attributes a preview as a monetized asset. */
  assetId?: string | null;
  /** Optional resolved chunk id in frame (attribution detail). Never fabricated. */
  chunkId?: string | null;
  /** Render only these blocks (a pagination window). When omitted, the whole
   *  document body renders (Storybook / single-page use). */
  blocks?: Block[];
  /** The SPR-05 resolver for citations. Defaults to the SPR-03 stub. */
  openDocument?: OpenDocument;
  /** Resolve a citation's source title for its hover affordance (M3). */
  resolveSourceTitle?: (sourceDocumentId: string) => string | undefined;
}

/**
 * Derive the table of contents from heading blocks — the SAME rule the Python
 * `Document.toc()` uses (derive-don't-duplicate; SPR-01). Walks the document's
 * full block list (not a page window) so the ToC is whole regardless of which
 * page is showing.
 */
export function deriveToc(blocks: Block[]): TocEntry[] {
  const entries: TocEntry[] = [];
  blocks.forEach((block, i) => {
    if (block.type === "heading") {
      entries.push({
        level: block.level,
        text: plainText(block.spans),
        block_index: i,
      });
    }
  });
  return entries;
}

/** Flatten inline spans to plain text for a ToC label (mirrors the Python
 *  `_spans_to_plain_text`: a citation contributes its marker, math its tex). */
function plainText(spans: import("../../types/document_model.gen").InlineSpan[]): string {
  const out: string[] = [];
  for (const span of spans) {
    switch (span.type) {
      case "text":
      case "code":
        out.push(span.text);
        break;
      case "math":
        out.push(span.tex);
        break;
      case "citation":
        out.push(span.marker);
        break;
      case "strong":
      case "emphasis":
      case "link":
        out.push(plainText(span.children));
        break;
    }
  }
  return out.join("");
}

const Reader = forwardRef<HTMLElement, ReaderProps>(function Reader(
  { document: doc, assetId, chunkId, blocks, openDocument, resolveSourceTitle },
  ref,
) {
  const rendered = blocks ?? doc.blocks ?? [];
  // Inherit from an outer ReaderProvider (a host that already supplied the real
  // SPR-05 resolver / a title resolver), and let explicit props override. This
  // means `<Reader>` works standalone (default stub) AND inside a host provider
  // without shadowing it.
  const outer = useReaderContext();
  const ctx = useMemo(
    () => ({
      openDocument: openDocument ?? outer.openDocument,
      resolveSourceTitle: resolveSourceTitle ?? outer.resolveSourceTitle,
    }),
    [openDocument, resolveSourceTitle, outer.openDocument, outer.resolveSourceTitle],
  );

  return (
    <ReaderProvider value={ctx}>
      <article
        ref={ref}
        data-reader-root
        // SPR-07 attribution markers — preserved verbatim from ReadingColumn:
        // tagged ONLY when a servable asset id is present (a gated preview leaves
        // the column untagged so a preview is never attributed); the chunk
        // marker is added ONLY when a real chunk id exists (never fabricated).
        {...(assetId ? { "data-akb-asset-id": assetId } : {})}
        {...(assetId && chunkId ? { "data-akb-chunk-id": chunkId } : {})}
        className="reader-body flex-1 font-serif text-[15px] leading-[1.7] text-ink dark:text-bright"
      >
        {rendered.length > 0 ? (
          <Blocks blocks={rendered} />
        ) : (
          <p className="text-shadow-1 dark:text-moonlight italic">
            This document has no readable content.
          </p>
        )}
      </article>
    </ReaderProvider>
  );
});

export default Reader;
