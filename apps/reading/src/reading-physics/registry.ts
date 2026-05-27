// ─────────────────────────────────────────────────────────────────────────
// The minimal facet registry (SPR-02, the proving slice).
//
// The registry is the SINK augmentations declare INTO (PR-1: declare, don't
// act). For the slice it implements only the `decorations` path of the frozen
// §6 `FacetRegistry` — `declareAnchoredWidget` / `declareSpatialTransform` are
// present (the frozen sink keeps SPR-04/05 from adding a new method) but
// COLLECT-ONLY: nothing enacts them this sprint. That is the deliberate
// smallness of the slice; SPR-03 generalizes the registry across all facets.
//
// PR-2 (no side store): the registry holds the declarations of a SINGLE
// render pass and nothing more. It is reconstructed every render from the
// augmentations + the substrate-derived doc model; losing it loses nothing
// (it is not a store of record). No localStorage / IndexedDB / persistence
// import lives here or anywhere under reading-physics/.
// ─────────────────────────────────────────────────────────────────────────

import { combineDecorations } from "./facets/decorations";
import type { ResolvedDecoration } from "./facets/decorations";
import type {
  AnchoredWidget,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
  SpatialTransform,
} from "./types";

/**
 * A FacetRegistry that collects declarations for one render pass. Implements
 * the frozen §6 sink. Decorations are combined (§5.1) on demand; the
 * widget/transform sinks collect for shape-completeness only (the slice does
 * not enact them — SPR-04/05).
 */
class CollectingRegistry implements FacetRegistry {
  private readonly decorations: Decoration[] = [];
  // Collected for frozen-shape completeness; NOT enacted this sprint (SPR-04/05).
  private readonly widgets: AnchoredWidget[] = [];
  private readonly transforms: SpatialTransform[] = [];

  declareDecoration(d: Decoration): void {
    this.decorations.push(d);
  }

  declareAnchoredWidget(w: AnchoredWidget): void {
    // Frozen sink; enacted by SPR-04. Collected so an augmentation that
    // declares one type-checks today without a surface change later.
    this.widgets.push(w);
  }

  declareSpatialTransform(t: SpatialTransform): void {
    // Frozen sink; enacted by SPR-05.
    this.transforms.push(t);
  }

  /** The combined, order-independent decoration set (§5.1) for this pass. */
  combinedDecorations(): ResolvedDecoration[] {
    return combineDecorations(this.decorations);
  }
}

/**
 * Run every augmentation's `contribute()` once against the given context and
 * return the COMBINED decoration set (§5.1). This is the collect → combine
 * half of the surface's collect → combine → enact cycle (§2); the surface
 * owns enact (the single apply pass that paints — PR-1).
 *
 * Pure with respect to augmentation code: each augmentation only declares into
 * the registry; this function never touches the DOM. The result is a
 * deterministic function of (augmentations, ctx) — order-independent across
 * augmentations because the combine rule sorts by a stable anchor key.
 */
export function collectDecorations(
  augmentations: readonly ReadingAugmentation[],
  ctx: ReadingContext,
): ResolvedDecoration[] {
  const registry = new CollectingRegistry();
  for (const aug of augmentations) {
    aug.contribute(ctx, registry);
  }
  return registry.combinedDecorations();
}
