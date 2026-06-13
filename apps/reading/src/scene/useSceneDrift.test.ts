/**
 * useSceneDrift.test.ts — the parallax BREATH invariants (ALC SPR-06 M4),
 * proven on the PURE `driftSeams` core (no DOM, no clock loop).
 *
 * The contract:
 *   • DETERMINISTIC: same (t, depths) → byte-identical transform strings (the
 *     fixed-clock snapshot stability the SPR-05 harness depends on).
 *   • BOUNDED: every plane's |dx|/|dy| ≤ depth × amplitude cap, and the cap is
 *     below the interactive pointer parallax (ambient must not out-shout intent).
 *   • RECESSION: the far plane (small depth) breathes LESS than the near plane.
 *   • NON-LOOPING: the planes' phases never re-align (prime periods) — checked by
 *     the period invariants in sceneMotion.test.ts; here we confirm the seam
 *     function actually USES distinct per-plane periods (two planes at the same t
 *     produce different phases).
 *   • REDUCED-MOTION: every seam is the identity (no transform) — the static pose.
 *   • TRANSFORM-ONLY: seams carry a translate transform and nothing layout-y.
 */
import { describe, expect, it } from "vitest";

import { driftSeams } from "./useSceneDrift";
import { DRIFT, PARALLAX } from "../design/motion/sceneMotion";
import { PLANE_DEPTHS } from "./layers/Mountainscape";

/** Parse the translate(xpx, ypx) a seam carries, for bound assertions. */
function parseTranslate(transform: string | undefined): { x: number; y: number } {
  const m = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/.exec(transform ?? "");
  if (!m) return { x: NaN, y: NaN };
  return { x: Number.parseFloat(m[1]), y: Number.parseFloat(m[2]) };
}

describe("driftSeams — determinism", () => {
  it("same (t, depths) → byte-identical seams (fixed-clock snapshot stability)", () => {
    const a = driftSeams(12_345, PLANE_DEPTHS);
    const b = driftSeams(12_345, PLANE_DEPTHS);
    expect(a).toEqual(b);
    // Transform strings are literally identical (the snapshot byte-diff gate).
    expect(a.map((s) => s.transform)).toEqual(b.map((s) => s.transform));
  });

  it("different t → generally different seams (the breath actually moves)", () => {
    const a = driftSeams(0, PLANE_DEPTHS);
    const b = driftSeams(5_000, PLANE_DEPTHS);
    expect(a.map((s) => s.transform)).not.toEqual(b.map((s) => s.transform));
  });
});

describe("driftSeams — bounded, sub-pointer-parallax amplitude", () => {
  it("every plane's |dx| ≤ depth × maxAmplitudePx and |dy| ≤ depth × maxAmplitudeYPx, across a sweep", () => {
    // Sweep a full set of phases; the sine extremes must respect the bound.
    for (let t = 0; t <= 60_000; t += 250) {
      const seams = driftSeams(t, PLANE_DEPTHS);
      seams.forEach((s, i) => {
        const { x, y } = parseTranslate(s.transform);
        const depth = PLANE_DEPTHS[i];
        // Allow a hair for the 3dp rounding.
        expect(Math.abs(x)).toBeLessThanOrEqual(depth * DRIFT.maxAmplitudePx + 0.001);
        expect(Math.abs(y)).toBeLessThanOrEqual(depth * DRIFT.maxAmplitudeYPx + 0.001);
      });
    }
  });

  it("the max possible breath (depth 1.0) stays UNDER the interactive pointer parallax cap", () => {
    expect(DRIFT.maxAmplitudePx).toBeLessThan(PARALLAX.pointerMaxPx);
  });
});

describe("driftSeams — aerial recession: far breathes less than near", () => {
  it("at the breath peak, the smallest-depth plane translates less than the largest-depth plane", () => {
    // Find each plane's peak |x| over a period sweep.
    const peak = PLANE_DEPTHS.map(() => 0);
    for (let t = 0; t <= 90_000; t += 100) {
      const seams = driftSeams(t, PLANE_DEPTHS);
      seams.forEach((s, i) => {
        const { x } = parseTranslate(s.transform);
        peak[i] = Math.max(peak[i], Math.abs(x));
      });
    }
    const minDepthIdx = PLANE_DEPTHS.indexOf(Math.min(...PLANE_DEPTHS));
    const maxDepthIdx = PLANE_DEPTHS.indexOf(Math.max(...PLANE_DEPTHS));
    expect(peak[minDepthIdx]).toBeLessThan(peak[maxDepthIdx]);
  });
});

describe("driftSeams — planes drift INDEPENDENTLY (distinct per-plane phase)", () => {
  it("two planes at the same t are at different phases (not a locked-step slide)", () => {
    // Pick a t where the sines differ; assert at least two planes' x differ in
    // a way not explained by depth alone (phase, not amplitude, differs).
    const t = 9_000;
    const seams = driftSeams(t, [1, 1, 1]); // equal depth isolates PHASE
    const xs = seams.map((s) => parseTranslate(s.transform).x);
    // With equal depth, distinct periods ⇒ distinct phases ⇒ distinct x.
    expect(new Set(xs).size).toBeGreaterThan(1);
  });
});

describe("driftSeams — reduced motion: the breath stops (static designed pose)", () => {
  it("every seam is the identity (no transform) under reduced motion", () => {
    const seams = driftSeams(12_345, PLANE_DEPTHS, true);
    seams.forEach((s) => {
      expect(s.transform).toBeUndefined();
      expect(s.opacity).toBeUndefined();
    });
    expect(seams).toHaveLength(PLANE_DEPTHS.length);
  });

  it("the reduced amplitude token is 0 (the breath is OFF, not merely small)", () => {
    expect(DRIFT.reducedAmplitudePx).toBe(0);
  });
});

describe("driftSeams — transform-only (GPU-cheap, no layout props)", () => {
  it("a running seam carries ONLY a translate transform (no width/height/top/left)", () => {
    const seams = driftSeams(3_333, PLANE_DEPTHS);
    seams.forEach((s) => {
      expect(s.transform).toMatch(/^translate\(/);
      expect(s.transform).not.toMatch(/width|height|top|left|margin|padding/);
    });
  });
});
