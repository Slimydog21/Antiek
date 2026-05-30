/**
 * Seedable, deterministic PRNG for the living mountainscape (SPR-04).
 *
 * WHY a custom PRNG and not Math.random():
 *   - Determinism is a HARD test requirement (milestone 2): "same seed →
 *     same frame N". Math.random() is unseedable, so a refactor could never
 *     be proven stable. A tiny seeded generator makes the whole procedural
 *     layer reproducible — clouds, snow, peak silhouettes all derive their
 *     positions from a seeded stream, so a snapshot of frame N is exact.
 *   - It is pure (no Date.now, no global state) so the SPR-02 placeholder
 *     guarantee (byte-stable) extends cleanly into our procedural composition.
 *
 * Algorithm: mulberry32 — a well-known, fast, good-enough 32-bit generator.
 * It is NOT cryptographic and does not need to be: we only need a stable,
 * uniformly-distributed stream for visual placement.
 */

/** A deterministic random source. `next()` returns a float in [0, 1). */
export interface Rng {
  next(): number;
  /** Float in [min, max). */
  range(min: number, max: number): number;
  /** Integer in [min, max] inclusive. */
  int(min: number, max: number): number;
}

/** Hash a string seed to a 32-bit unsigned integer (FNV-1a). Deterministic. */
export function seedFromString(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32 — deterministic given the same numeric seed. */
export function makeRng(seed: number): Rng {
  let a = seed >>> 0;
  const next = (): number => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    next,
    range: (min: number, max: number) => min + next() * (max - min),
    int: (min: number, max: number) => Math.floor(min + next() * (max - min + 1)),
  };
}
