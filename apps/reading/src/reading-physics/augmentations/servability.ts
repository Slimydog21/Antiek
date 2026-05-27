// ─────────────────────────────────────────────────────────────────────────
// ServabilityAugmentation — the §9.0 servability / IP-holder annotations,
// re-homed from MasterMdViewer's inline SourceCitation into a DECLARED
// augmentation (SPR-02 M3, the proving slice).
//
// This is the proof: a real, SHIPPED reading behavior (the §9.0 gate's
// visible expression on a cited source) re-expressed as a Decoration
// contribution into the `decorations` facet, with a BYTE-IDENTICAL render.
// It is the one re-homed augmentation the slice de-risks SPR-03 with.
//
// PR-1 (declare, don't act): this module DECLARES; it never touches the DOM.
// PR-2 (no side store): it reads the substrate-derived source model handed to
//   it; it persists nothing and imports no persistence client.
// PR-6 (substrate verdict is upstream): it READS `servable` (the §9.0 verdict
//   the substrate's getChunk endpoint supplies) and NEVER recomputes it. The
//   augmentation has no power to override §9.0 — a non-servable source's
//   className declares the restricted treatment, and it declares NOTHING that
//   could reveal a withheld body or a withheld owner (the endpoint already
//   withheld both; the augmentation only annotates the verdict it was given).
//
// The closed-vocabulary className (§5.1: "a closed vocabulary the surface
// understands, NOT arbitrary CSS") is how the augmentation declares WHAT —
// the servability verdict — while the surface owns HOW it paints (which DOM
// branch). The surface maps `SERVABLE_CLASS` → the openable citation and
// `RESTRICTED_CLASS` → the honest "not available to open" state, producing
// byte-for-byte the same classes/widgets the inline code produced.
// ─────────────────────────────────────────────────────────────────────────

import type {
  ChunkId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

// ── The closed servability vocabulary (the WHAT; §5.1) ───────────────────
//
// These are NOT the painted CSS classes — they are the closed verdict
// vocabulary the surface understands and maps to its concrete treatment.
// Keeping the verdict words distinct from the design-token classes is what
// lets the augmentation declare WHAT (servable vs restricted) without owning
// HOW the surface paints it (PR-1 / PR-5: what is separate from where/how).

export const SERVABLE_CLASS = "servability--servable";
export const RESTRICTED_CLASS = "servability--restricted";

/** The exact tooltip the inline restricted branch carried (byte-equivalence).
 *  Note the typographic apostrophe (’), matching MasterMdViewer.tsx verbatim. */
export const RESTRICTED_TITLE =
  "This source isn’t available to open here (its license restricts it).";
/** The exact tooltip the inline servable branch carried. */
export const SERVABLE_TITLE = "Click to preview · ⌘-click to open the source";

/**
 * The per-source view the augmentation reads. This is the adaptation boundary
 * for OQ4 (canon §9 open question 4): the canon's frozen `ReadonlySynthesis`
 * is opaque-minimal and does not carry resolved sources, while the real shipped
 * surface resolves a `ResolvedSource` (servable + ipHolderName + a
 * representative chunk id) from `getChunk`. SPR-02 adapts the real resolved
 * shape to the frozen decorations path at the surface boundary: the surface
 * resolves the sources (as it already did via `getChunk` — PR-6: the substrate
 * supplies `servable`), then hands this minimal, substrate-derived shape to the
 * augmentation, which DECLARES a Decoration per source. The augmentation invents
 * nothing — every field here originates in the substrate's getChunk verdict.
 *
 * `representativeChunkId` is the source's substrate-minted anchor (PR-4): the
 * closest semantic identity to "this source" the frozen Anchor vocabulary
 * offers (a source groups chunks of one document; the representative chunk is
 * its handle). This is the documented OQ4 adaptation — flagged, not a silent
 * fork of the frozen signature.
 */
export interface ServabilitySourceView {
  /** The source's representative chunk id (the decoration's anchor). */
  readonly representativeChunkId: string;
  /** §9.0 verdict, READ from the substrate (PR-6), never recomputed. */
  readonly servable: boolean;
}

/**
 * Build the §9.0 servability augmentation over a set of resolved sources.
 *
 * The augmentation is a pure function from the (resolved) sources to a set of
 * Decoration declarations: one per source, anchored to the source's
 * representative chunk, carrying the closed-vocabulary verdict class + the
 * matching tooltip. It returns nothing and mutates nothing (PR-1).
 *
 * WHY a factory over a fixed singleton: the sources are render-scoped
 * (resolved per claim, per render), so the augmentation closes over the
 * substrate-derived sources for THIS render — still pure w.r.t. its inputs,
 * still side-effect-free. It does not cache across renders (PR-2: no side
 * store; losing it loses nothing — the next render re-resolves from getChunk).
 */
export function makeServabilityAugmentation(
  sources: readonly ServabilitySourceView[],
): ReadingAugmentation {
  return {
    id: "servability",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const source of sources) {
        const decoration: Decoration = {
          anchor: {
            kind: "chunk",
            chunkId: source.representativeChunkId as ChunkId,
          },
          // PR-6: the verdict is the substrate's `servable`, read not recomputed.
          // A non-servable source declares ONLY the restricted class — nothing
          // here can reveal the body/owner the endpoint already withheld.
          className: source.servable ? SERVABLE_CLASS : RESTRICTED_CLASS,
          title: source.servable ? SERVABLE_TITLE : RESTRICTED_TITLE,
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
