// ─────────────────────────────────────────────────────────────────────────
// SkimAugmentation — rhetorical-role colors (SPR-06 M1). The talk's "Skim"
// (Fauconnier et al., re-grounded on Antiek): light up each claim/sentence by
// its rhetorical role — objective GREEN, method BLUE, result ORANGE — so a
// reader can skim a synthesis by structure.
//
// Skim is HALF of the SPR-06 composability proof. It declares colored-background
// decorations into the SPR-03 `decorations` facet and NOTHING else. It does not
// know SiteSee (the other half) exists; the two meet only at the facet (PR-3).
// Their composition is the deliverable — see skim-sitesee.compose.test.ts.
//
// ── THE OPEN QUESTION: where does the role come from? (resolved) ───────────
//
// Diligence (synthesisParser.ts): `ParsedClaim` / `thesis_components` carry NO
// explicit rhetorical-role field — only { index, claim, rationale, confidence,
// effectiveSourceTier, hedgingRequired, chunkIds, supportingPathIndices }. So
// Skim must DERIVE the role. The canon PR-2 + the sprint manual give two paths:
//   (a) derive a COARSE role from the synthesis STRUCTURE itself (a claim's
//       position / section / heading), OR
//   (b) run a classifier and write its output to the SUBSTRATE as an event
//       (NEVER a private store — that violates PR-2, breaks composition, and
//       trips the SPR-03 guard).
//
// RESOLUTION: path (a), STRUCTURE — no classifier, no event write. The
// synthesis structure already partitions content into distinct rhetorical
// buckets, and the substrate already stamps each chunk a `section_path`. The
// SURFACE resolves a coarse role per claim from those substrate-derived signals
// (see `RhetoricalRoleView` below) and hands them in; Skim only DECLARES a
// color per role. This keeps Skim contract-only (imports ONLY `../types`, like
// servability/ip-holder), keeps it pure (PR-1), and makes the no-data state
// honest: a synthesis with no resolved roles declares NOTHING — no guessed
// colors (M5). Path (b)'s classifier-event is the documented fallback if a
// future synthesis genuinely needs per-sentence roles structure can't give; it
// is NOT needed for the coarse claim-level signal this sprint ships, and a
// coarse honest role that composes beats a precise one that doesn't (manual).
// The taxonomy + the structure→role mapping live in reading-physics/README.md.
//
// PR-1 (declare, don't act): this module DECLARES decorations; it never touches
//   the DOM. The closed-vocabulary className is the WHAT (the role); the surface
//   owns HOW it paints the color (PR-5).
// PR-2 (no side store): the roles are substrate-derived (synthesis structure +
//   chunk section_path), handed in by the surface; this stores nothing and
//   imports no persistence client. It writes NO classifier event (path a).
// PR-3 (named facets only): imports the facet contract (../types) and nothing
//   from another augmentation — not SiteSee, with which it composes.
// PR-6 (substrate upstream): the role is read from substrate-derived structure,
//   never a verdict this augmentation recomputes; it writes nothing.
// PR-8 (agent-authorable): imports ONLY `../types`.
// ─────────────────────────────────────────────────────────────────────────

import type {
  ClaimId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

// ── The rhetorical-role taxonomy (the WHAT; §5.1 closed vocabulary) ────────
//
// FOUR coarse roles. "other" is the explicit HONEST bucket for content whose
// role the structure does not determine — Skim declares NOTHING for "other"
// (no guessed color), exactly as it declares nothing for an unclassified claim.
// The roles are deliberately coarse (the sprint manual: a coarse honest signal
// that composes beats a precise classifier that doesn't ship).

export type RhetoricalRole = "objective" | "method" | "result" | "other";

// The closed-vocabulary className per role — the WHAT the surface paints, NOT
// the painted CSS. The surface maps each verdict word to its concrete color
// treatment (objective → green, method → blue, result → orange), exactly as the
// servability augmentation's SERVABLE_CLASS / RESTRICTED_CLASS verdict words map
// to its concrete branches. "other" has NO class — it is the no-color bucket.
export const SKIM_OBJECTIVE_CLASS = "skim--objective";
export const SKIM_METHOD_CLASS = "skim--method";
export const SKIM_RESULT_CLASS = "skim--result";

/** The role → closed-vocabulary className map. `other` → null (no color).
 *  A single source of truth so the surface and the augmentation agree. */
export function classForRole(role: RhetoricalRole): string | null {
  switch (role) {
    case "objective":
      return SKIM_OBJECTIVE_CLASS;
    case "method":
      return SKIM_METHOD_CLASS;
    case "result":
      return SKIM_RESULT_CLASS;
    case "other":
      return null; // honest: no role determined ⇒ no color (M5).
  }
}

/** The human-readable role label the surface may paint as an aria/tooltip.
 *  Kept here so the closed vocabulary has one home. */
export function titleForRole(role: RhetoricalRole): string | null {
  switch (role) {
    case "objective":
      return "Objective";
    case "method":
      return "Method";
    case "result":
      return "Result";
    case "other":
      return null;
  }
}

/**
 * The per-claim role view Skim reads (M1) — the adaptation boundary for the
 * open question. The canon's frozen `ReadonlySynthesis` is opaque-minimal
 * (question + claims with ids/chunkIds) and carries no role, so the SURFACE
 * resolves a coarse role per claim from substrate-derived structure (the
 * synthesis section the claim sits in + the chunk's `section_path`) and hands
 * this minimal shape to the augmentation. The augmentation invents nothing —
 * every role here originates in substrate structure, resolved upstream (PR-6).
 *
 * `claimId` is the claim's synthesis-scoped positional anchor (PR-4); the role
 * decoration anchors to the claim, so it follows the claim under any transform
 * and lands on the SAME range a SiteSee citation tint on that claim would —
 * which is exactly the overlap case the composition proof tests (a cited
 * sentence that is also a "result").
 */
export interface RhetoricalRoleView {
  /** The claim's synthesis-scoped positional anchor (PR-4 semantic). */
  readonly claimId: string;
  /** The coarse role the surface resolved from substrate structure. */
  readonly role: RhetoricalRole;
}

/**
 * Build the Skim augmentation (M1) over a set of resolved per-claim roles.
 *
 * A pure function from the (resolved) roles to a set of Decoration
 * declarations: one colored-background decoration per claim whose role is
 * objective/method/result, anchored to the CLAIM. A claim with role "other"
 * (or absent from the input) declares NOTHING — the honest no-classification
 * state (M5): no guessed color. It returns nothing and mutates nothing (PR-1).
 *
 * WHY a factory over a fixed singleton (matches servability/ip-holder): the
 * roles are render-scoped (resolved per synthesis, per render from substrate
 * structure), so the augmentation closes over the substrate-derived roles for
 * THIS render — still pure w.r.t. its inputs, no cross-render cache (PR-2).
 *
 * The decoration carries the closed-vocabulary role class + a role title; it
 * does NOT carry an `attribution` or a `widget`, so when it merges on the same
 * claim range with a SiteSee citation tint, the combined class set is exactly
 * { Skim's role class, SiteSee's tint class } and neither augmentation knows the
 * other contributed (PR-3 — the M3 composition). The decorations facet's
 * order-independent union is what makes that merge deterministic.
 */
export function makeSkimAugmentation(
  roles: readonly RhetoricalRoleView[],
): ReadingAugmentation {
  return {
    id: "skim",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const r of roles) {
        const className = classForRole(r.role);
        // "other" / no determined role ⇒ no class ⇒ declare nothing (M5).
        // No fabricated color for content the structure didn't classify.
        if (className === null) continue;
        const title = titleForRole(r.role);
        const decoration: Decoration = {
          anchor: { kind: "claim", claimId: r.claimId as ClaimId },
          className,
          ...(title ? { title } : {}),
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
