import { makeRng } from "./rng";

/**
 * Deterministic mountain-ridge generator (SPR-04, milestone 2 — Peaks).
 *
 * Produces a normalized ridge polyline (a midpoint-displacement / fractal
 * silhouette) for a seed. Pure + deterministic so the peaks are the same every
 * run for a given mood seed. The Peaks layer renders these as SVG polygons in
 * parallax bands; keeping the GEOMETRY here (not in the component) makes the
 * silhouette unit-testable and reusable by ProceduralSky for the fallback.
 *
 * Returns an array of {x,y} in [0,1]×[0,1] where y is the ridge HEIGHT from the
 * bottom (1 = tall peak, 0 = valley). The caller flips/scales into pixels.
 */
export interface RidgePoint {
  x: number;
  y: number;
}

/** Midpoint-displacement ridge. `roughness` in (0,1): higher = jaggier.
 *  `base`/`amp` set the band's valley floor and peak amplitude. */
export function makeRidge(
  seed: number,
  opts: { points?: number; roughness?: number; base?: number; amp?: number } = {},
): RidgePoint[] {
  const points = opts.points ?? 17; // power-of-two + 1 for clean subdivision
  const roughness = opts.roughness ?? 0.55;
  const base = opts.base ?? 0.25;
  const amp = opts.amp ?? 0.45;
  const rng = makeRng((seed ^ 0x9ea50) >>> 0);

  // Heights array, subdivided by midpoint displacement.
  const n = points - 1;
  const heights = new Array<number>(points).fill(0);
  heights[0] = rng.range(0.3, 0.7);
  heights[n] = rng.range(0.3, 0.7);

  let step = n;
  let scale = 1;
  while (step > 1) {
    const half = step / 2;
    for (let i = half; i < points; i += step) {
      const left = heights[i - half];
      const right = heights[i + half] ?? left;
      const mid = (left + right) / 2;
      heights[i] = mid + (rng.next() * 2 - 1) * scale * roughness;
    }
    step = half;
    scale *= 0.5;
  }

  return heights.map((hRaw, i) => {
    const h = Math.max(0, Math.min(1, hRaw));
    return { x: i / n, y: base + h * amp };
  });
}

/**
 * The three parallax peak BANDS (far → near). Each is a ridge seed offset +
 * its parallax depth (how strongly it shifts with the pointer) + a relative
 * vertical placement. Documented so the layering is explicit and bounded.
 *
 * PARALLAX BOUND (anti-nausea, milestone 2 acceptance): `depth` is the MAX
 * fraction of MAX_PARALLAX_PX a band shifts. Far peaks barely move (depth
 * 0.25), near peaks move most (depth 1.0) — but the absolute cap is small
 * (see MAX_PARALLAX_PX) so even full pointer travel produces a gentle shift.
 */
export interface PeakBand {
  seedOffset: number;
  /** parallax strength 0..1 (× MAX_PARALLAX_PX). */
  depth: number;
  /** vertical anchor (fraction of height from the top the band's base sits). */
  anchor: number;
  ridge: { points: number; roughness: number; base: number; amp: number };
}

/** Absolute parallax cap in px. Pointer travel of the full viewport maps to at
 *  most ±8px of scene shift — deliberately tiny so it reads as depth, never as
 *  motion sickness. This is the documented anti-nausea ceiling. */
export const MAX_PARALLAX_PX = 8;

export const PEAK_BANDS: PeakBand[] = [
  {
    seedOffset: 0x11,
    depth: 0.25,
    anchor: 0.42,
    ridge: { points: 17, roughness: 0.4, base: 0.18, amp: 0.3 },
  },
  {
    seedOffset: 0x22,
    depth: 0.55,
    anchor: 0.58,
    ridge: { points: 17, roughness: 0.55, base: 0.22, amp: 0.4 },
  },
  {
    seedOffset: 0x33,
    depth: 1.0,
    anchor: 0.78,
    ridge: { points: 17, roughness: 0.7, base: 0.28, amp: 0.5 },
  },
];

/** Build an SVG path `d` for a ridge band, given the band's ridge points and a
 *  100×100 viewBox. The polygon closes down to the bottom so it fills as a
 *  silhouette. `yShift` (px, already parallax-bounded) nudges the band. */
export function ridgePathD(points: RidgePoint[], yShift = 0): string {
  const pts = points
    .map((p) => `${(p.x * 100).toFixed(2)},${(100 - p.y * 100 + yShift).toFixed(2)}`)
    .join(" L ");
  return `M -2,102 L ${pts} L 102,102 Z`;
}
