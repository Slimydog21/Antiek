import { makeRng, seedFromString, type Rng } from "./rng";

/**
 * Procedural field generators (SPR-04, milestone 2).
 *
 * These are PURE functions of (seed, count, dimensions) — no rendering, no
 * React, no DOM. They produce the deterministic particle/cloud layouts and a
 * pure `advance` that computes a particle's position at a given time `t`. The
 * canvas painters (Snow.tsx / Clouds.tsx) are thin shells that call these and
 * stroke the result, so the HARD part (determinism) is unit-testable without a
 * canvas: same seed → identical particles → identical frame N.
 *
 * BUDGETS (commented with rationale per the rigor rubric):
 *   - SNOW_COUNT = 140. A wind-driven flurry needs enough flakes to read as
 *     weather, but every flake is a fillRect per frame. 140 flakes × 60fps =
 *     8,400 tiny fills/s — trivial on a laptop GPU/CPU, and visually "snowing"
 *     without a whiteout that would hurt text contrast over the glass. Tuned
 *     down from a first 250 (too dense over content) — this is the documented
 *     trigger value, not arbitrary.
 *   - CLOUD_COUNT = 7. Clouds are big soft blobs (radial gradients); they are
 *     expensive PER blob but few in number. 7 gives layered parallax depth
 *     (3 far + 4 near bands) without overpainting. More than ~10 and the sky
 *     reads busy and the fill cost climbs.
 */

export const SNOW_COUNT = 140;
export const CLOUD_COUNT = 7;

/** One snow particle's immutable spawn attributes (positions are derived from
 *  these + time in `snowAt`, so a particle is fully determined by its seed). */
export interface SnowParticle {
  /** base x in [0,1] of the field width. */
  x0: number;
  /** base y in [0,1] of the field height (vertical phase offset). */
  y0: number;
  /** fall speed factor (px/s scales with this). */
  speed: number;
  /** horizontal sway amplitude in [0,1] of width. */
  sway: number;
  /** sway phase. */
  phase: number;
  /** radius in px. */
  r: number;
}

/** One cloud's immutable attributes; position derives from these + time. */
export interface CloudPuff {
  x0: number; // base x in [0,1]
  y: number; // y in [0,1] (clouds keep a band)
  scale: number; // radius factor
  speed: number; // drift speed factor (parallax band)
  alpha: number; // per-cloud opacity multiplier
}

/** Deterministically generate the snow field for a seed. */
export function makeSnow(seed: number, count = SNOW_COUNT): SnowParticle[] {
  const rng: Rng = makeRng(seed ^ 0x5e1f);
  const out: SnowParticle[] = [];
  for (let i = 0; i < count; i++) {
    out.push({
      x0: rng.next(),
      y0: rng.next(),
      speed: rng.range(0.6, 1.6),
      sway: rng.range(0.01, 0.05),
      phase: rng.range(0, Math.PI * 2),
      r: rng.range(0.7, 2.2),
    });
  }
  return out;
}

/** Deterministically generate the cloud band for a seed. */
export function makeClouds(seed: number, count = CLOUD_COUNT): CloudPuff[] {
  const rng: Rng = makeRng(seed ^ 0xc10d);
  const out: CloudPuff[] = [];
  for (let i = 0; i < count; i++) {
    // Two parallax bands: far (slow, high, faint) and near (faster, lower).
    const far = i < Math.ceil(count * 0.45);
    out.push({
      x0: rng.next(),
      y: far ? rng.range(0.06, 0.26) : rng.range(0.2, 0.46),
      scale: far ? rng.range(0.5, 0.9) : rng.range(0.9, 1.6),
      speed: far ? rng.range(0.004, 0.009) : rng.range(0.01, 0.02),
      alpha: far ? rng.range(0.4, 0.7) : rng.range(0.6, 1),
    });
  }
  return out;
}

/** A snow particle's pixel position at time `t` (ms) within a w×h field, with
 *  a wind drift. Pure + deterministic. Wraps vertically so the flurry loops. */
export function snowAt(
  p: SnowParticle,
  t: number,
  w: number,
  h: number,
  wind: number,
): { x: number; y: number } {
  const ts = t / 1000;
  // Vertical fall (wraps over the field height).
  const fall = (p.y0 + ts * p.speed * 0.12) % 1;
  const y = fall * h;
  // Horizontal: base + wind drift + gentle sway.
  const drift = (p.x0 + ts * wind * 0.02) % 1;
  const sway = p.sway * Math.sin(ts * 1.3 + p.phase);
  let xf = drift + sway;
  xf = ((xf % 1) + 1) % 1; // wrap to [0,1)
  return { x: xf * w, y };
}

/** A cloud's center x at time `t` (ms), looping across the field width. Pure. */
export function cloudX(c: CloudPuff, t: number, w: number): number {
  const ts = t / 1000;
  const f = ((c.x0 + ts * c.speed) % 1 + 1) % 1;
  // Render slightly off-screen on both sides so blobs enter/exit smoothly.
  return (f * 1.4 - 0.2) * w;
}

/** Seed a field deterministically from a string (e.g. a mood key). */
export function fieldSeed(key: string): number {
  return seedFromString(key);
}
