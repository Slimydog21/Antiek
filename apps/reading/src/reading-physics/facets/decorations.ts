// ─────────────────────────────────────────────────────────────────────────
// `decorations` facet — the minimal combine rule (SPR-02, the proving slice).
//
// This is the SEED that SPR-03 generalizes into the full facet engine + CI
// guard. It implements EXACTLY ONE facet (decorations) from the frozen §6
// signature — no anchored-widgets, no spatial-transform, no multi-render, no
// registry generalization beyond decorations (those are SPR-03/04/05; the
// sprint deliberately resists them). The point of the slice is to prove the
// Physics of Reading on real, shipped code with a byte-identical render — not
// to build the engine.
//
// PR-1 (declare, don't act): augmentations only DECLARE Decoration values via
// the registry; this module COMBINES them into a deterministic, resolved set.
// The surface owns the single apply pass that paints the combined result —
// nothing here touches the DOM.
// ─────────────────────────────────────────────────────────────────────────

import type { Anchor, Decoration } from "../types";

/**
 * A canonical, collision-free string key for a semantic anchor (§5.1 "same
 * range"). Two decorations are "on the same range" iff their anchors produce
 * the same key. The key is derived purely from the anchor's semantic fields
 * (PR-4: never a pixel), so it is stable across renders / themes / transforms.
 *
 * WHY a key (defensibility): the combine rule must be order-independent — it
 * must not matter which augmentation declared first. A string key gives us a
 * total, stable ordering and an exact same-range equality test without
 * depending on object identity or declaration order.
 */
export function anchorKey(anchor: Anchor): string {
  switch (anchor.kind) {
    case "chunk":
      return `chunk:${anchor.chunkId}`;
    case "claim":
      return `claim:${anchor.claimId}`;
    case "passage":
      // Half-open [start, end) into the chunk's text (PR-4: chunk-relative,
      // not DOM-relative). Encoded so distinct passages of the same chunk get
      // distinct keys.
      return `passage:${anchor.chunkId}:${anchor.start}:${anchor.end}`;
  }
}

/**
 * A decoration after combine: one resolved range, the UNION of every class
 * set declared on it, and the deterministically-joined title set. This is
 * what the surface's apply pass enacts — one painted treatment per range.
 */
export interface ResolvedDecoration {
  /** The anchor every contributing decoration shared (same key ⇒ same range). */
  readonly anchor: Anchor;
  /** The stable key, exposed so the apply pass can index by range cheaply. */
  readonly key: string;
  /** The union of every declared class (whitespace-split, de-duplicated),
   *  sorted lexicographically so the painted class string is order-independent. */
  readonly classNames: readonly string[];
  /** The set of declared titles on this range, sorted and joined by " · "
   *  (§5.1). Empty string ⇒ no title was declared (the surface omits it). */
  readonly title: string;
}

/** Split a className string into individual classes, dropping empties. */
function splitClasses(className: string): string[] {
  return className.split(/\s+/).filter((c) => c.length > 0);
}

/**
 * COMBINE RULE (frozen §5.1): range UNION, deterministic, ORDER-INDEPENDENT.
 *
 * - Decorations are grouped by anchor key (§5.1 "same range"). Two decorations
 *   on the SAME range merge: their classes union, their titles join.
 * - Within a range, classes are the de-duplicated union of every contributing
 *   className, SORTED lexicographically — so the painted class string is a
 *   pure function of the SET of declarations, never of declaration order.
 * - Titles on the same range are collected into a SET, sorted lexicographically,
 *   and joined by " · " (§5.1) — again order-independent.
 * - The resolved ranges themselves are returned SORTED by anchor key.
 *
 * WHY sort everywhere (defensibility / the whole point of the slice): the
 * combine must be order-independent so two augmentations never depend on the
 * order they happen to be enabled in. CodeMirror's facet model gets free
 * composition exactly because the combine is a deterministic function of the
 * SET of contributions; sorting by a stable key is how we make that true here.
 * SPR-03 generalizes this combine across the other facets — this is its seed.
 *
 * Edge cases (rigor #3):
 *   - empty input          → [] (no-op);
 *   - two decorations, one range, overlapping/identical → merged class union
 *     + joined titles, BYTE-IDENTICAL regardless of declaration order;
 *   - a decoration with an empty className → contributes no class (no crash);
 *   - a decoration with no title → contributes no title fragment.
 */
export function combineDecorations(
  decorations: readonly Decoration[],
): ResolvedDecoration[] {
  // Group by stable anchor key. We accumulate a class SET and a title SET per
  // range so the result is independent of input order.
  const byKey = new Map<
    string,
    { anchor: Anchor; classes: Set<string>; titles: Set<string> }
  >();

  for (const d of decorations) {
    const key = anchorKey(d.anchor);
    let entry = byKey.get(key);
    if (!entry) {
      entry = { anchor: d.anchor, classes: new Set(), titles: new Set() };
      byKey.set(key, entry);
    }
    for (const c of splitClasses(d.className)) entry.classes.add(c);
    if (d.title) entry.titles.add(d.title);
  }

  const resolved: ResolvedDecoration[] = [];
  for (const [key, entry] of byKey) {
    resolved.push({
      anchor: entry.anchor,
      key,
      classNames: [...entry.classes].sort(),
      // §5.1: the SET of titles, sorted, joined by " · ".
      title: [...entry.titles].sort().join(" · "),
    });
  }

  // Order-independent output: resolved ranges sorted by their stable key.
  resolved.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return resolved;
}
