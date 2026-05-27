// ─────────────────────────────────────────────────────────────────────────
// _template.ts — the authoring-kit starting point (SPR-08 M1).
//
// Copy this file, rename it (`<your-idea>.ts`), and fill in your idea where the
// "AGENT: FILL IN" comments are. It already:
//   - imports ONLY the facet API barrel (`../types`) — inside the PR-8 allowlist;
//   - implements the frozen §6 `ReadingAugmentation` contract (id + contribute);
//   - reads substrate-derived data at DECLARE time (`ReadingContext`) and
//     CAPTURES it in a closure — so it never touches a substrate field at render;
//   - declares ONE trivial `Decoration` via `registry.declareDecoration` — the
//     simplest facet, no geometry, no widget;
//   - compiles under the repo's strict tsconfig and passes
//     `tools/lint/reading_physics_check.py` AS-IS.
//
// Read `../AUTHORING_KIT.md` for the full contract, the safety gates, and the
// worked examples (servability / skim / quality-cue / accrual). Read the shipped
// augmentations in this folder before you author — they are the worked examples.
//
// The PR invariants this template already obeys (the guard enforces them):
//   PR-1 (declare, don't act): it DECLARES into a facet; it never touches the DOM.
//   PR-2 (no side store): it reads substrate-derived data handed in; stores none.
//   PR-3 (named facets only): it imports the facet barrel, no sibling augmentation.
//   PR-4 (semantic anchors): it anchors to a `claim` id, never a pixel.
//   PR-8 (agent-authorable): it imports ONLY `../types` — the contract alone.
// ─────────────────────────────────────────────────────────────────────────

import type {
  ClaimId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

// ── 1. Your closed-vocabulary verdict word (the WHAT; §5.1) ────────────────
//
// A decoration's `className` is a CLOSED VOCABULARY the surface understands and
// maps to its concrete paint — NOT arbitrary CSS, NOT inline DOM (PR-1). Export
// one constant per treatment so the surface and the augmentation agree on the
// word. The surface owns HOW the word paints; you only declare WHICH word.
//
// AGENT: FILL IN — replace this with the verdict word(s) your idea paints.
export const TEMPLATE_CLASS = "template--example";

// ── 2. The substrate-derived view your augmentation reads (PR-2) ───────────
//
// The frozen `ReadonlySynthesis` (on `ctx.synthesis`) is opaque-minimal
// (question + claims with ids/chunkIds). When your idea needs more than that —
// a §9.0 verdict, an IP-holder name, a resolved title — the SURFACE resolves it
// from the substrate (via the shipped `getChunk`, exactly as it already does)
// and hands you THIS minimal, substrate-derived shape. You invent nothing; every
// field here originates in the substrate (PR-2 / PR-6). The factory below closes
// over a list of these for ONE render — pure, no cross-render cache.
//
// AGENT: FILL IN — replace these fields with the substrate-derived data your
// idea needs. Keep `claimId` (or a `representativeChunkId`) so you have an anchor.
export interface TemplateItemView {
  /** The claim's synthesis-scoped positional anchor (PR-4 semantic), e.g. "1". */
  readonly claimId: string;
}

/**
 * Build the augmentation over the (substrate-derived) items for one render.
 *
 * A FACTORY over a fixed singleton because the data is render-scoped — it is
 * resolved per synthesis, per render (like servability/skim/quality-cue). The
 * augmentation closes over the items for THIS render: still pure w.r.t. its
 * inputs, still side-effect-free, no cache that survives a reload (PR-2 — losing
 * the closure loses nothing; the next render re-resolves from the substrate).
 *
 * `contribute(ctx, registry)` is the entire surface area you write (PR-1):
 *   - `ctx` is the DECLARE-TIME `ReadingContext` — `ctx.synthesis`, `ctx.layout`,
 *     `ctx.substrate`. Read substrate data HERE; do NOT read it inside a widget's
 *     render closure (that closure gets the render-time `RenderContext`, which has
 *     NO substrate field — see AUTHORING_KIT.md "ReadingContext vs RenderContext");
 *   - `registry` is the sink: `declareDecoration` / `declareAnchoredWidget` /
 *     `declareSpatialTransform`. You DECLARE; the surface combines + enacts.
 *
 * It returns nothing and mutates nothing.
 */
export function makeTemplateAugmentation(
  items: readonly TemplateItemView[],
): ReadingAugmentation {
  return {
    // Stable id — for diagnostics + multi-render reconciliation. Unique per
    // augmentation. AGENT: FILL IN — name it for your idea.
    id: "template",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      // AGENT: FILL IN — your idea goes here. This trivial version declares one
      // decoration per item, anchored to the item's claim (PR-4 semantic), with
      // the closed-vocabulary verdict word. The surface paints it; you don't.
      //
      // To declare a WIDGET instead, build an `AnchoredWidget` (id + anchor +
      // lane + weight + a pure `render(rect, ctx)` returning a ReactNode) and
      // call `registry.declareAnchoredWidget(...)`. For a HEAVY widget, return a
      // surface-injected component from `ctx.components` rather than importing it
      // (see AUTHORING_KIT.md + accrual.ts / chase-launcher.ts).
      for (const item of items) {
        const decoration: Decoration = {
          anchor: { kind: "claim", claimId: item.claimId as ClaimId },
          className: TEMPLATE_CLASS,
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
