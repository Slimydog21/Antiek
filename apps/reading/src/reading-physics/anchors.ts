// ─────────────────────────────────────────────────────────────────────────
// Shared semantic-anchor helpers (SPR-04 M3).
//
// A NON-augmentation module (it lives at reading-physics/ root, NOT under
// augmentations/) so multiple augmentations may import these helpers WITHOUT
// violating PR-3 (which forbids augmentation→augmentation imports, but allows
// the facet API barrel / other physics modules). The "synthesis-header anchor"
// is a SURFACE-LEVEL concept shared by QualityCue + AccrualView; putting it here
// keeps each augmentation from owning it and the others importing a sibling.
//
// PR-4: every helper produces a SEMANTIC anchor (the frozen `Anchor` union),
// never a pixel. The synthesis header has no substrate-minted chunk id, so the
// closest semantic handle the frozen vocabulary offers is the FIRST claim's
// anchor — the synthesis-scoped positional index `data-claim-id="1"` that the
// surface already stamps (MasterMdViewer.tsx:164). The header sits at the top of
// the synthesis, above claim 1, so claim 1's anchor is the nearest semantic
// "top of this synthesis." It is PR-4-clean (a claim index, not a pixel) and
// stable for the lifetime of the rendered synthesis.
// ─────────────────────────────────────────────────────────────────────────

import type { Anchor, ClaimId } from "./types";

/**
 * The claim id the synthesis-header anchor uses (the first claim, index 1). A
 * branded `ClaimId` so callers get the opaque-handle type, not a free string.
 */
export const SYNTHESIS_HEADER_CLAIM_ID = "1" as ClaimId;

/**
 * The semantic anchor for "the synthesis header" (M3/M4): the first claim's
 * anchor. Shared by QualityCue and AccrualView so both pin to the SAME anchor —
 * which is exactly the §5.2 case the de-overlap handles (two widgets at one
 * anchor stack by weight, ties by id). PR-4-clean.
 */
export function synthesisHeaderAnchor(): Anchor {
  return { kind: "claim", claimId: SYNTHESIS_HEADER_CLAIM_ID };
}
