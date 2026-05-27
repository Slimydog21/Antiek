// ─────────────────────────────────────────────────────────────────────────
// The facet registry + augmentation lifecycle (SPR-03 M1/M3; generalizes the
// SPR-02 seed).
//
// SPR-02 shipped a `CollectingRegistry` that knew only about decorations.
// SPR-03 GENERALIZES it into a per-facet collecting registry: it implements the
// frozen §6 `FacetRegistry` sink (declareDecoration / declareAnchoredWidget /
// declareSpatialTransform) by routing every declaration into a per-facet
// bucket keyed by facet name, then resolves a facet by running THAT facet's
// combine rule (M1 `Facet`) over its bucket. `collectDecorations` is preserved
// as the surface's decorations entry point so MasterMdViewer + the SPR-02
// byte-equivalence test are unchanged — it now delegates to the generic path.
//
// PR-1 (declare, don't act): the registry is a SINK. An augmentation's
// `contribute()` only pushes declarations; this module never touches the DOM.
//
// PR-2 (no side store): the registry holds the declarations of a SINGLE render
// pass and nothing more. It is reconstructed every render from the enabled
// augmentations + the substrate-derived context; losing it loses nothing (it is
// not a store of record). No localStorage / IndexedDB / persistence import
// lives here or anywhere under reading-physics/.
//
// PR-3 (named facets are the only coupling): augmentations interact ONLY by
// declaring into named facets the registry collects; no augmentation imports
// another. The registry is the surface-owned meeting point.
// ─────────────────────────────────────────────────────────────────────────

import { decorationsFacet } from "./facets/decorations";
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
 * A FacetRegistry that collects declarations for ONE render pass, bucketed by
 * facet name. Implements the frozen §6 sink. The decorations bucket is resolved
 * by the decorations facet's combine rule (§5.1); the widget/transform buckets
 * collect for frozen-shape completeness only (the surface does not enact them
 * until SPR-04/05).
 *
 * Generic on purpose (M1): a facet is identified by name; routing a declaration
 * is "push into the bucket named like the facet." SPR-04/05 add no new sink
 * method — they only start enacting the buckets that already collect.
 */
class CollectingRegistry implements FacetRegistry {
  // Per-facet buckets keyed by facet name. A single map keeps the registry
  // generic over the facet roster (M1) rather than hard-coding one field per
  // facet — adding a facet is registering its name, not editing this class.
  private readonly buckets = new Map<string, unknown[]>();

  private bucket<T>(name: string): T[] {
    let b = this.buckets.get(name) as T[] | undefined;
    if (!b) {
      b = [];
      this.buckets.set(name, b);
    }
    return b;
  }

  declareDecoration(d: Decoration): void {
    this.bucket<Decoration>(decorationsFacet.name).push(d);
  }

  declareAnchoredWidget(w: AnchoredWidget): void {
    // Frozen sink; enacted by SPR-04. Collected so an augmentation that
    // declares one type-checks today without a surface change later.
    this.bucket<AnchoredWidget>("anchored-widgets").push(w);
  }

  declareSpatialTransform(t: SpatialTransform): void {
    // Frozen sink; enacted by SPR-05.
    this.bucket<SpatialTransform>("spatial-transform").push(t);
  }

  /** The combined, order-independent decoration set (§5.1) for this pass —
   *  produced by running the decorations facet's combine rule over its bucket
   *  (M1: the surface owns the combine; this just applies it). */
  combinedDecorations(): ResolvedDecoration[] {
    return decorationsFacet.combine(this.bucket<Decoration>(decorationsFacet.name));
  }
}

/**
 * Run every augmentation's `contribute()` once against the given context and
 * return the COMBINED decoration set (§5.1). This is the collect → combine
 * half of the surface's collect → combine → enact cycle (§2); the surface owns
 * enact (the single apply pass that paints — PR-1).
 *
 * Pure with respect to augmentation code: each augmentation only declares into
 * the registry; this function never touches the DOM. The result is a
 * deterministic function of (augmentations, ctx) — order-independent across
 * augmentations because the facet's combine rule sorts by a stable anchor key.
 *
 * NOTE the caller passes the augmentations it wants run — which IS the enable
 * set (M3). `resolveEnabled` below is the lifecycle-aware front door; this
 * lower-level entry point is kept so the SPR-02 surface + byte-equivalence test
 * are unchanged.
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

// ── Augmentation lifecycle (M3) ───────────────────────────────────────────
//
// Enabling/disabling an augmentation adds/removes EXACTLY its contributions,
// with no residue — which proves PR-1 (augmentations don't act; the system
// composes whatever is currently enabled). Because `contribute()` is pure and
// the registry is rebuilt every pass (PR-2: no side store), "disable" is simply
// "don't run it next pass" — there is nothing to clean up, no listener to tear
// down, no DOM to revert. That property is the whole point: a stateful plugin
// would leave residue; a declarative augmentation cannot.

/**
 * An immutable enable set. `enable`/`disable` return a NEW set (no mutation), so
 * a render reads a snapshot and the next render reads the next snapshot — there
 * is no shared mutable lifecycle state to leak (PR-2). Augmentations are keyed
 * by their stable `id`; enabling the same id twice is idempotent, disabling an
 * absent id is a no-op.
 */
export class EnabledAugmentations {
  private readonly byId: ReadonlyMap<string, ReadingAugmentation>;

  constructor(augmentations: readonly ReadingAugmentation[] = []) {
    const m = new Map<string, ReadingAugmentation>();
    for (const a of augmentations) m.set(a.id, a);
    this.byId = m;
  }

  /** Return a new set with `aug` enabled (replaces any same-id augmentation). */
  enable(aug: ReadingAugmentation): EnabledAugmentations {
    const next = new Map(this.byId);
    next.set(aug.id, aug);
    return EnabledAugmentations.fromMap(next);
  }

  /** Return a new set with the augmentation `id` removed (no-op if absent). */
  disable(id: string): EnabledAugmentations {
    if (!this.byId.has(id)) return this;
    const next = new Map(this.byId);
    next.delete(id);
    return EnabledAugmentations.fromMap(next);
  }

  has(id: string): boolean {
    return this.byId.has(id);
  }

  /** The enabled augmentations, ordered by `id` so the SET — not the
   *  enable order — determines the run order. The combine rules are
   *  order-independent regardless, but a stable run order makes the registry's
   *  behavior reproducible and the order-independence test meaningful. */
  list(): readonly ReadingAugmentation[] {
    return [...this.byId.values()].sort((a, b) =>
      a.id < b.id ? -1 : a.id > b.id ? 1 : 0,
    );
  }

  private static fromMap(m: Map<string, ReadingAugmentation>): EnabledAugmentations {
    return new EnabledAugmentations([...m.values()]);
  }
}

/**
 * Resolve the combined decoration set for whatever is CURRENTLY enabled (M3).
 * The lifecycle-aware front door: disabling an augmentation removes exactly its
 * contributions because the registry is rebuilt from the current enable set and
 * the disabled augmentation simply isn't run — no residue (PR-1).
 */
export function resolveEnabled(
  enabled: EnabledAugmentations,
  ctx: ReadingContext,
): ResolvedDecoration[] {
  return collectDecorations(enabled.list(), ctx);
}
