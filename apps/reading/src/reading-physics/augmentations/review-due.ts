// ─────────────────────────────────────────────────────────────────────────
// review-due.ts — a spaced-repetition "review-due" cue (SPR-08 M3).
//
// In the spirit of Quantum Country: the page nudges memory consolidation by
// marking the claims a reader is *due to review*. It reads a substrate-derived
// "review state" view (which claims are due) — the dormant-correct, read-only
// pattern the kit describes for history-style data (AUTHORING_KIT.md §2 + #7):
// the SURFACE resolves the review state from the substrate and hands it to this
// factory; the augmentation only READS the resolved view and DECLARES into a
// facet. It never invents a private store, never writes the substrate, and
// never fabricates review state when there is none.
//
// Facet: a single `Decoration` per due claim — a closed-vocabulary verdict word
// (`review-due`) the surface paints onto the claim's range, plus an optional
// aria/title string. Decorations are the simplest facet (no geometry, no widget,
// no React), so this composes with Skim/SiteSee/etc. on the same claim range for
// free (range UNION, order-independent — AUTHORING_KIT.md §4a / §5.1). A spatial
// transform is deliberately NOT declared (surface-reserved until SPR-05 — §3/#8).
//
// The PR invariants this module obeys (the guard enforces them):
//   PR-1 (declare, don't act): it DECLARES one decoration per due claim; no DOM.
//   PR-2 (no side store): it reads the substrate-derived view handed in; stores none.
//   PR-3 (named facets only): it imports the facet barrel, no sibling augmentation.
//   PR-4 (semantic anchors): it anchors to a `claim` id, never a pixel.
//   PR-6 (no write path): it READS the review-due verdict; never recomputes/writes it.
//   PR-8 (agent-authorable): it imports ONLY `../types` — the contract alone.
// ─────────────────────────────────────────────────────────────────────────

import type {
  ClaimId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

// ── 1. The closed-vocabulary verdict word (the WHAT; §4a / §5.1) ───────────
//
// A decoration's `className` is a CLOSED VOCABULARY the surface maps to its
// concrete paint — NOT arbitrary CSS, NOT inline DOM (PR-1). One constant, one
// verdict word: "this claim is due for review." The surface owns HOW the
// review-due highlight looks; this augmentation only declares WHICH word.
export const REVIEW_DUE_CLASS = "review-due";

// ── 2. The substrate-derived review-state view this augmentation reads (PR-2) ─
//
// The SURFACE resolves the reader's spaced-repetition schedule from the
// substrate and hands this factory ONE minimal, substrate-derived view per
// claim that is currently due for review. Every field originates in the
// substrate (PR-2 / PR-6): `claimId` is the synthesis-scoped positional anchor
// (PR-4 semantic), and the optional `dueLabel` is a substrate-resolved,
// human-readable cue (e.g. "Due today" / "Overdue") the surface may surface as
// the decoration's title. The factory closes over a list of these for ONE
// render — pure, no cross-render cache (losing the closure loses nothing; the
// next render re-resolves from the substrate).
//
// Honest no-data is structural: the surface passes ONLY the due claims, so when
// the reader has no review state, or nothing is due, the list is empty and the
// loop below declares nothing. This augmentation never fabricates a due claim.
export interface ReviewDueClaimView {
  /** The due claim's synthesis-scoped positional anchor (PR-4 semantic), e.g. "1". */
  readonly claimId: string;
  /**
   * Optional substrate-resolved review cue for the aria/title (e.g. "Due today",
   * "Overdue by 2 days"). Plain text, substrate-supplied; never fabricated. Omit
   * when the substrate resolved no label — the decoration then carries no title.
   */
  readonly dueLabel?: string;
}

/**
 * Build the review-due augmentation over the (substrate-derived) due claims for
 * one render.
 *
 * A FACTORY over the render-scoped review state, exactly like
 * servability/skim/quality-cue: the augmentation closes over THIS render's due
 * claims — pure w.r.t. its inputs, side-effect-free, no cache that survives a
 * reload (PR-2).
 *
 * `contribute(ctx, registry)` is the entire surface area (PR-1):
 *   - `ctx` is the DECLARE-TIME `ReadingContext` (has `substrate`); this
 *     augmentation needs no further substrate read — the surface already
 *     resolved the review state — so `ctx` is unused (prefixed `_ctx`).
 *   - `registry` is the sink; this augmentation declares only decorations.
 *
 * It returns nothing and mutates nothing.
 */
export function makeReviewDueAugmentation(
  dueClaims: readonly ReviewDueClaimView[],
): ReadingAugmentation {
  return {
    id: "review-due",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      // Honest no-data: an empty `dueClaims` (no review state, or nothing due)
      // declares nothing — no guessed highlights. This loop simply does not run.
      for (const claim of dueClaims) {
        const decoration: Decoration = {
          anchor: { kind: "claim", claimId: claim.claimId as ClaimId },
          className: REVIEW_DUE_CLASS,
          // Only attach a title when the substrate resolved a cue — never a
          // fabricated default. Two decorations on the same range with titles
          // are joined deterministically by the surface (sorted, " · ").
          ...(claim.dueLabel !== undefined ? { title: claim.dueLabel } : {}),
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
