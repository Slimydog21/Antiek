/**
 * peaks.test.ts — SPR-04 milestone 2: the peak ridge is deterministic +
 * bounded, and the parallax ceiling is small (anti-nausea).
 */
import { describe, expect, it } from "vitest";

import { makeRidge, MAX_PARALLAX_PX, PEAK_BANDS, ridgePathD } from "./peaks";

describe("ridge generator — deterministic + in-bounds", () => {
  it("same seed → identical ridge", () => {
    expect(makeRidge(777)).toEqual(makeRidge(777));
  });

  it("different seeds diverge", () => {
    expect(makeRidge(1)).not.toEqual(makeRidge(2));
  });

  it("ridge y stays within [0,1]", () => {
    for (const p of makeRidge(42, { roughness: 0.9 })) {
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(1);
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(1);
    }
  });

  it("ridgePathD produces a closed SVG path", () => {
    const d = ridgePathD(makeRidge(5));
    expect(d.startsWith("M ")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
  });
});

describe("parallax ceiling — anti-nausea", () => {
  it("the absolute parallax cap is small (<= 12px)", () => {
    // A documented anti-nausea ceiling: even full pointer travel must be a
    // gentle shift, not a lurch.
    expect(MAX_PARALLAX_PX).toBeLessThanOrEqual(12);
  });

  it("near bands move more than far bands, all within the cap", () => {
    const depths = PEAK_BANDS.map((b) => b.depth);
    // far → near is increasing depth.
    expect(depths[0]).toBeLessThan(depths[depths.length - 1]);
    for (const b of PEAK_BANDS) {
      // worst-case shift = depth × cap × |pointer in [-1,1]| ≤ cap.
      expect(b.depth * MAX_PARALLAX_PX).toBeLessThanOrEqual(MAX_PARALLAX_PX);
    }
  });
});
