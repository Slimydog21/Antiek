/**
 * pinBody.ts — the pin request body for one selection, pure (anchor-first
 * SPR-02). The §9.0 rule at the pin boundary, in one pure function:
 *
 *   - a SERVABLE selection posts its quote (+ the context the host located),
 *     and the server resolves canonically;
 *   - a WITHHELD selection's text NEVER leaves the client — it resolves the
 *     chunk + offsets LOCALLY (the anchor-map is hashes+ids, lawful to hold)
 *     and posts ids/numbers only: the explicit metadata-only form with NO
 *     quote field anywhere in the body.
 *
 * A selection with no unique in-page location pins nothing (null — never a
 * guessed anchor), whatever its servability.
 */
import type { CreateAnchorBody } from "../../lib/api";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import { outboundText } from "../shared/FloatMenu/floatMenuActions";

export interface SelectionLocation {
  chunkId: string;
  /** Chunk-relative [start, end). */
  start: number;
  end: number;
  /** The selection's offset in the normalized served body. */
  bodyOffset: number;
}

export function buildPinBody(
  source: string,
  sel: FloatMenuSelection,
  loc: SelectionLocation | null,
  normalizedBody: string,
  pageIndex: number,
): CreateAnchorBody | null {
  const safe = outboundText(sel);
  if (safe === null) {
    // Metadata-only: ids/numbers only — no quote field anywhere.
    if (!loc) return null;
    return {
      node_id: loc.chunkId,
      start_scalar: loc.start,
      end_scalar: loc.end,
      page_index_hint: pageIndex,
      source,
    };
  }
  return {
    quote: safe,
    prefix: loc
      ? normalizedBody.slice(Math.max(0, loc.bodyOffset - 32), loc.bodyOffset)
      : "",
    suffix: loc
      ? normalizedBody.slice(
          loc.bodyOffset + sel.text.length,
          loc.bodyOffset + sel.text.length + 32,
        )
      : "",
    page_index_hint: pageIndex,
    source,
  };
}
