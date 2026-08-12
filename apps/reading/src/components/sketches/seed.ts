/**
 * Deterministic seed helpers for Processing-style sketches.
 *
 * Algorithm choice mirrors the house scene + arcade substrate:
 *   - FNV-1a 32-bit for string → u32 seed (artifact ids map to stable visuals)
 *   - mulberry32 for the PRNG stream
 *
 * We re-implement (not re-export) so sketch modules stay self-contained and
 * do not couple to scene/ or arcade/ import paths. Byte-compatible with
 * apps/reading/src/scene/rng.ts.
 */

import type { SketchRng } from "./types";

/** Hash a string seed to a 32-bit unsigned integer (FNV-1a). Deterministic. */
export function seedFromString(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Coerce a string | number seed into a u32 for mulberry32. */
export function coerceSeed(seed: string | number): number {
  if (typeof seed === "number") {
    // Ensure finite → u32. NaN / Infinity collapse to 0 (stable, not random).
    if (!Number.isFinite(seed)) return 0;
    return seed >>> 0;
  }
  return seedFromString(seed);
}

/** mulberry32 — deterministic given the same numeric seed. */
export function makeRng(seed: number): SketchRng {
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
    int: (min: number, max: number) =>
      Math.floor(min + next() * (max - min + 1)),
  };
}

/** Convenience: make a PRNG directly from a string|number seed. */
export function rngFromSeed(seed: string | number): SketchRng {
  return makeRng(coerceSeed(seed));
}
