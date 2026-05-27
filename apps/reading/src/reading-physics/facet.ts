// ─────────────────────────────────────────────────────────────────────────
// The generic facet runtime (SPR-03 M1).
//
// SPR-02 proved the physics on ONE hand-rolled facet (decorations): a fixed
// `combineDecorations` + a `CollectingRegistry` that only knew about
// decorations. This module GENERALIZES that seed into a reusable `Facet<T, R>`
// — a named combine rule the surface owns — without changing the decorations
// facet's rendered output. The decorations facet is re-expressed in terms of
// this `Facet` (facets/decorations.ts), and the SPR-02 byte-equivalence test
// stays green because the combine ALGORITHM is byte-for-byte the same; only
// its packaging moved behind the generic shape.
//
// WHY a generic Facet (the talk's lesson, §4 of the canon): the surface
// composes N augmentations in O(facets), not O(N²), precisely because every
// cross-augmentation concern is a NAMED facet with ONE combine rule the surface
// owns. A `Facet<T, R>` makes that "one combine rule" a first-class value:
//   - augmentations declare T-shaped contributions (never act — PR-1);
//   - the surface collects every enabled augmentation's contributions and runs
//     the facet's `combine(T[]) => R` to resolve them;
//   - `combine` is a pure function of the SET of contributions, so the result
//     is independent of the order augmentations were enabled in (PR-3 / §4).
//
// PR-2 (no side store): a Facet holds NO data of its own. It is a combine rule
// plus identity metadata — a value, not a store. The registry holds the
// declarations of a SINGLE render pass and is reconstructed every render.
// ─────────────────────────────────────────────────────────────────────────

/**
 * A named composition rule the reading surface owns. `TContribution` is what an
 * augmentation declares into the facet; `TResolved` is what the surface gets
 * after combining every contribution for one render pass.
 *
 * A facet is a VALUE (a combine rule + identity), never a store — it holds no
 * per-render state (that lives in the registry, rebuilt each pass, PR-2). The
 * surface registers a fixed set of facets once and runs `combine` per pass.
 */
export interface Facet<TContribution, TResolved> {
  /** Stable facet name (e.g. "decorations"). Used as the registry's bucket key
   *  and in diagnostics. Two facets must never share a name. */
  readonly name: string;
  /**
   * Z-ORDER PRIORITY (M2 / defensibility). When two facets paint treatments
   * that can visually overlap, the surface stacks them by ascending `priority`
   * — a HIGHER priority paints on top (nearer the reader). This is a property
   * of the FACET, fixed by the surface, NOT of the declaration order: which
   * augmentation declared first is irrelevant to the z-order, so composition
   * stays order-independent (PR-3). Ties between facets (equal priority) are an
   * authoring error the surface rejects via `assertDistinctPriorities`.
   */
  readonly priority: number;
  /**
   * THE combine rule (PR-1 / PR-3). A PURE function from the set of declared
   * contributions to the resolved result. MUST be order-independent: combining
   * a shuffled `contributions` array yields a value deep-equal to the original
   * (the surface relies on this so no augmentation depends on enable order).
   * The decorations facet enforces this by sorting on a stable semantic key
   * before producing output (facets/decorations.ts).
   */
  combine(contributions: readonly TContribution[]): TResolved;
}

/**
 * Define a facet. A thin constructor so a facet is declared in one place with
 * its name, z-order priority, and combine rule together — the surface's roster
 * of facets is then a list of these.
 */
export function defineFacet<TContribution, TResolved>(
  def: Facet<TContribution, TResolved>,
): Facet<TContribution, TResolved> {
  return def;
}

/**
 * Assert that a set of facets have DISTINCT z-order priorities (M2 /
 * defensibility). Equal priorities would make the stacking order of two
 * overlapping facets depend on something other than `priority` — exactly the
 * order-dependence the physics forbids. The surface calls this once over its
 * facet roster; a duplicate is an authoring error, surfaced loudly rather than
 * resolved silently. Returns the facets sorted by ascending priority (the
 * paint order: lower first, higher on top).
 */
export function assertDistinctPriorities(
  facets: readonly Facet<unknown, unknown>[],
): readonly Facet<unknown, unknown>[] {
  const byPriority = new Map<number, string>();
  for (const f of facets) {
    const clash = byPriority.get(f.priority);
    if (clash !== undefined) {
      throw new Error(
        `Facet z-order priority collision: "${f.name}" and "${clash}" both ` +
          `declare priority ${f.priority}. Each facet must have a distinct ` +
          `priority so the paint stacking order is deterministic (PR-3).`,
      );
    }
    byPriority.set(f.priority, f.name);
  }
  return [...facets].sort((a, b) => a.priority - b.priority);
}
