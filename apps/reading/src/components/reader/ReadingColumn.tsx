import { forwardRef } from "react";

/**
 * ReadingColumn — the calm, centered reading body that renders a servable
 * work's text INSIDE the shell-level SPR-07 ad border (Read SPR-09 M3).
 *
 * It does NOT mount the border (AdBorderMount owns that at the shell). It
 * renders the page body in the working region the border frames, and — the
 * load-bearing reason this component exists — it TAGS the rendered IP content
 * with the per-second attribution markers SPR-07's `useFrameAttention` scans
 * for:
 *
 *   • `data-akb-asset-id` — the document/asset id, the trace anchor. Per the
 *     frame contract (components/ad/frameContract.ts) the ASSET is the
 *     monetized unit and the asset id IS the document id. Without this marker
 *     the sampler finds nothing in the working region and every second is a
 *     house second — the whole per-second attribution layer is a permanent
 *     no-op. Tagging it here is what closes that SPR-07 prerequisite.
 *   • `data-akb-chunk-id` — OPTIONAL trace detail for the specific chunk in
 *     frame. Set ONLY when a real, resolved chunk id exists. We never fabricate
 *     one (rigor #1: honesty over coverage) — the books read path does not yet
 *     expose per-chunk ids for the linear body, so `chunkId` is normally
 *     undefined and the sample carries the asset id alone, which is correct
 *     (the contract treats a missing chunk id as "asset-level, no chunk
 *     detail", exactly the cover/title-card case).
 *
 * §9.0: the caller (the reader) only ever renders gate-served text — a gated or
 * taken-down work's full body never reaches this component (it shows a
 * preview/withheld notice instead and does NOT render a tagged IP body). So a
 * `data-akb-asset-id`-tagged column is, by construction, only ever a SERVABLE
 * asset: attribution can never accrue to withheld text.
 *
 * The column is centered and width-capped so the surrounding ad border never
 * overlaps or pushes the prose: the border reserves its band via the SPR-06
 * `--akb-border-inset-*` seam on the shell frame, and this column's own
 * max-width sits well inside that reserved working region at every viewport.
 */

export interface ReadingColumnProps {
  /** The document/asset id — stamped as `data-akb-asset-id` so the SPR-07
   *  sampler attributes in-frame seconds to this asset.
   *
   *  §9.0 GATE: pass this ONLY when the gate served the FULL text (a servable
   *  asset). Pass `null`/omit for a gated preview snippet — a metadata-tier
   *  preview is NOT the monetizable full asset and must not be attributed. The
   *  reader column is then untagged and the sampler correctly counts the second
   *  as a house second over a non-asset preview. The selection scope (the
   *  forwarded `<article>` ref) is preserved either way. */
  assetId?: string | null;
  /** The served body for the current page (gate-permitted markdown). */
  text: string;
  /** HTML is accepted only when the server's sanitize-on-write provenance
   * marks this exact stored body as trusted. */
  contentFormat?: "text" | "html";
  /** OPTIONAL resolved chunk id for the page in frame. Omit when no real chunk
   *  id is available — never pass a synthetic one (no fabricated coverage). */
  chunkId?: string | null;
}

/**
 * Render a page's markdown body as readable prose: `#`/`##`/`###` lines become
 * headings, blank-line-separated runs become paragraphs. Deliberately light —
 * the served body is already cleaned text, not rich markup.
 */
function renderBlocks(text: string) {
  const blocks = text
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean);
  return blocks.map((block, i) => {
    const heading = block.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      return (
        <h2
          key={i}
          className="font-serif font-semibold text-lg mt-4 mb-2 text-ink dark:text-bright"
        >
          {heading[2]}
        </h2>
      );
    }
    return (
      <p key={i} className="mb-3 whitespace-pre-wrap">
        {block}
      </p>
    );
  });
}

/**
 * The tagged reading body. A forwardRef so the reader can keep using it as the
 * float-menu selection SCOPE (the same `<article>` the shared
 * useFloatMenuSelection hook listens inside) — wiring it in is a one-line swap
 * for the reader's old inline body, with the attribution markers added.
 */
export const ReadingColumn = forwardRef<HTMLElement, ReadingColumnProps>(
  function ReadingColumn({ assetId, text, chunkId, contentFormat = "text" }, ref) {
    return (
      <article
        ref={ref}
        // The two SPR-07 attribution markers. The sampler scans the working
        // region for [data-akb-asset-id]; this is the element it finds for a
        // servable book reading session. Both markers are added only when their
        // value is truthy — never an empty/fabricated attribute. A null assetId
        // (a gated preview) leaves the column untagged, so the sampler never
        // attributes a preview snippet as a monetized asset (§9.0). An unresolved
        // chunk stays asset-level (the contract's cover/title-card case).
        {...(assetId ? { "data-akb-asset-id": assetId } : {})}
        {...(assetId && chunkId ? { "data-akb-chunk-id": chunkId } : {})}
        className="flex-1 font-serif text-[15px] leading-[1.7] text-ink dark:text-bright"
      >
        {text.trim() ? (
          contentFormat === "html" ? (
            <div data-antiek-html-body dangerouslySetInnerHTML={{ __html: text }} />
          ) : renderBlocks(text)
        ) : (
          <p className="text-shadow-1 dark:text-moonlight italic">
            This book has no readable pages.
          </p>
        )}
      </article>
    );
  },
);

export default ReadingColumn;
