import { describe, expect, it } from "vitest";

import {
  ROD_BUTT_LOCAL,
  ROD_TIP_LOCAL,
  catenaryPath,
  rodBend,
  rodLength,
  rodTipFromMascotRect,
} from "./fishingLineGeometry";

describe("catenaryPath", () => {
  it("sags on a long span", () => {
    const d = catenaryPath({ x: 0, y: 0 }, { x: 200, y: 0 });
    expect(d).toMatch(/^M 0 0 Q 100 [\d.]+ 200 0$/);
    const match = d.match(/Q 100 ([\d.]+) 200/);
    expect(Number(match![1])).toBeGreaterThan(0);
  });

  it("the sag dips BELOW the straight tip→bait chord (reads as a hanging line)", () => {
    // A horizontal span: the chord midpoint is at y=0, the catenary control y
    // must be strictly below it (greater y in screen space) → the line hangs.
    const d = catenaryPath({ x: 0, y: 0 }, { x: 200, y: 0 });
    const cy = Number(d.match(/Q 100 ([\d.]+) 200/)![1]);
    expect(cy).toBeGreaterThan(0);
  });

  it("ends at the live bait instrument point (cursor is bait densify)", () => {
    // Fixed-station densify: free end of the line is the cursor/bait, not a chase.
    const bait = { x: 300, y: 400 };
    const d = catenaryPath({ x: 10, y: 20 }, bait);
    expect(d.startsWith("M 10 20 ")).toBe(true);
    expect(d.endsWith(" 300 400")).toBe(true);
  });

  it("degenerates to a straight segment when span < 8px", () => {
    expect(catenaryPath({ x: 0, y: 0 }, { x: 4, y: 0 })).toBe("M 0 0 L 4 0");
  });

  it("never produces NaN coordinates (dist == 0)", () => {
    const d = catenaryPath({ x: 10, y: 10 }, { x: 10, y: 10 });
    expect(d).not.toContain("NaN");
  });

  it("stays finite across a short-distance sweep (dist < 8, the settle regime)", () => {
    // SPR-04 M4: no NaN/Infinity anywhere in the < 8px (settle-epsilon) band.
    for (let d = 0; d < 8; d += 0.5) {
      const path = catenaryPath({ x: 100, y: 100 }, { x: 100 + d, y: 100 });
      expect(path).not.toContain("NaN");
      expect(path).not.toContain("Infinity");
      for (const n of path.match(/-?\d+(\.\d+)?/g) ?? []) {
        expect(Number.isFinite(Number(n))).toBe(true);
      }
    }
  });
});

describe("rod-tip contract (SPR-04)", () => {
  it("the default localTip is the new rod tip ROD_TIP_LOCAL, NOT the old (50,22) stub", () => {
    const rect = { left: 0, top: 0 } as DOMRect;
    const tip = rodTipFromMascotRect(rect, 64);
    expect(tip).toEqual(ROD_TIP_LOCAL); // scale = 64/64 = 1 ⇒ screen == local
    // Guard the regression: the old shoulder point must be gone.
    expect(ROD_TIP_LOCAL).not.toEqual({ x: 50, y: 22 });
  });

  it("the rod is at least 2× the old (44,30)→(50,22) stub length", () => {
    // M2 acceptance: total rod length ≥ 2× baseline, asserted against geometry.
    const OLD_STUB_LEN = Math.hypot(50 - 44, 22 - 30); // = 10
    expect(rodLength()).toBeGreaterThanOrEqual(2 * OLD_STUB_LEN);
    // Sanity: rodLength is butt→tip of the SHARED contract.
    expect(rodLength()).toBeCloseTo(
      Math.hypot(
        ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x,
        ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y,
      ),
    );
  });

  it("the line's FIRST point coincides with the rod tip across rendered sizes", () => {
    // M3/M4 + rigor #3: localTip feeds screen-space math at scale = size/64.
    // Prove the catenary's first point lands on the rod tip at every size the
    // mascot can render at, NOT just MASCOT_SIZE=64.
    for (const size of [32, 64, 96, 128]) {
      const rect = { left: 200, top: 120 } as DOMRect;
      const tip = rodTipFromMascotRect(rect, size);
      const scale = size / 64;
      // Expected screen-space tip from the contract + the documented transform.
      expect(tip.x).toBeCloseTo(rect.left + ROD_TIP_LOCAL.x * scale, 6);
      expect(tip.y).toBeCloseTo(rect.top + ROD_TIP_LOCAL.y * scale, 6);
      // And the line the layer draws actually STARTS there (within tolerance).
      const bait = { x: tip.x + 300, y: tip.y + 200 };
      const d = catenaryPath(tip, bait);
      const m = d.match(/^M (-?[\d.]+) (-?[\d.]+) /)!;
      expect(Number(m[1])).toBeCloseTo(tip.x, 6);
      expect(Number(m[2])).toBeCloseTo(tip.y, 6);
    }
  });

  it("an explicit localTip still overrides the default (caller contract intact)", () => {
    const rect = { left: 10, top: 5 } as DOMRect;
    const tip = rodTipFromMascotRect(rect, 64, { x: 1, y: 2 });
    expect(tip).toEqual({ x: 11, y: 7 });
  });
});

describe("rodBend (tension model, SPR-04 M2)", () => {
  it("a near bait yields a straighter rod than a far bait (monotone in distance)", () => {
    let prev = -Infinity;
    for (let dist = 0; dist <= 400; dist += 10) {
      const bend = rodBend(dist);
      expect(bend).toBeGreaterThanOrEqual(prev); // never decreases with distance
      prev = bend;
    }
  });

  it("rest (distance 0) is dead straight; far casts approach but never exceed MAX", () => {
    expect(rodBend(0)).toBe(0);
    expect(rodBend(10)).toBeGreaterThan(0);
    expect(rodBend(10)).toBeLessThan(rodBend(100));
    // Saturating: even an absurd distance can't bend it past the cap.
    expect(rodBend(1e6)).toBeLessThanOrEqual(6);
    expect(rodBend(1e6)).toBeGreaterThan(5.9);
  });

  it("negative/garbage distance clamps to a straight rod (no NaN)", () => {
    expect(rodBend(-50)).toBe(0);
    expect(Number.isFinite(rodBend(0))).toBe(true);
  });
});
