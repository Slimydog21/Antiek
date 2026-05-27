// ─────────────────────────────────────────────────────────────────────────
// IpHolderAugmentation — the "whose work grounds this" IP-holder annotation,
// re-homed from MasterMdViewer's inline `owner` string into a DECLARED
// augmentation (SPR-03 M5; the first real TWO-augmentation composition).
//
// SPR-10 M1 shipped the IP-holder annotation hand-wired into SourceCitation:
// `const owner = source.ipHolderName ? ", published by X" : ""`. SPR-03
// re-expresses it as its OWN decorations augmentation that declares an
// `attribution` payload on the SAME source anchor the servability augmentation
// decorates. The facet merges the two contributions per §5.1; the surface reads
// the verdict class (servability's) and the owner name (this augmentation's)
// off ONE combined decoration. Neither augmentation imports the other (PR-3) —
// they meet only at the named `decorations` facet. That is the composition the
// physics is for.
//
// PR-1 (declare, don't act): this module DECLARES an attribution; it never
//   touches the DOM.
// PR-2 (no side store): it reads the substrate-derived source model handed to
//   it; it persists nothing and imports no persistence client.
// PR-3 (named facets are the only coupling): it imports the facet API (types)
//   and nothing from another augmentation — not even servability, with which it
//   composes. The composition happens at the facet, not via an import.
// PR-6 (substrate verdict is upstream): the owner name is the substrate's
//   `ip_holder_name`, READ never invented. It declares attribution ONLY when
//   the substrate resolved a non-null owner — so it can never fabricate an
//   owner, and it never declares attribution for a withheld/non-servable source
//   (the endpoint already returned ip_holder_name = null there, §9.0).
// ─────────────────────────────────────────────────────────────────────────

import type {
  ChunkId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

/**
 * The per-source view the IP-holder augmentation reads — the same substrate-
 * derived shape the servability augmentation consumes (resolved by the surface
 * via the shipped `getChunk`), narrowed to what attribution needs: the source's
 * representative chunk (its anchor, PR-4) and the substrate's resolved owner
 * name. `ipHolderName` is `string | null` because the substrate returns null
 * when the owner is unknown OR the source is non-servable (§9.0 withholds the
 * owner with the body); the augmentation declares attribution only for the
 * non-null case (honest unknown — never an invented owner).
 */
export interface IpHolderSourceView {
  /** The source's representative chunk id (the decoration's anchor). */
  readonly representativeChunkId: string;
  /** §9.0 / SPR-10: the resolved IP-holder name, or null (unknown OR withheld).
   *  READ from the substrate (PR-6), never invented. */
  readonly ipHolderName: string | null;
}

/**
 * Build the IP-holder augmentation over a set of resolved sources.
 *
 * A pure function from the (resolved) sources to a set of Decoration
 * declarations: one attribution decoration per source that HAS a known owner,
 * anchored to the source's representative chunk (the SAME anchor servability
 * uses — that is how the two compose). A source with a null owner declares
 * NOTHING (honest unknown). It returns nothing and mutates nothing (PR-1).
 *
 * The decoration carries an empty `className` (the IP-holder augmentation owns
 * no verdict class — only attribution data), so when it merges with the
 * servability decoration on the same range, the combined class set is exactly
 * servability's verdict class plus nothing, and the combined attribution is
 * this augmentation's owner name. Byte-equivalence with the inline render is
 * preserved: the surface paints "published by <name>" iff the combined
 * decoration carries exactly one IP-holder name (the single-owner case).
 */
export function makeIpHolderAugmentation(
  sources: readonly IpHolderSourceView[],
): ReadingAugmentation {
  return {
    id: "ip-holder",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const source of sources) {
        // PR-6: declare attribution ONLY for a substrate-resolved, non-null
        // owner. A null owner (unknown OR §9.0-withheld) declares nothing —
        // the surface then paints no "published by …", the honest unknown.
        if (!source.ipHolderName) continue;
        const decoration: Decoration = {
          anchor: {
            kind: "chunk",
            chunkId: source.representativeChunkId as ChunkId,
          },
          // No verdict class — the IP-holder augmentation contributes only the
          // attribution payload. (An empty className contributes no class to
          // the combined set, so it never collides with servability's verdict.)
          className: "",
          attribution: { ipHolderName: source.ipHolderName },
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
