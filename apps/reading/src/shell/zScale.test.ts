/**
 * zScale.test.ts — the F-1/F-2 stacking invariant, proven (ALC SPR-08 M1).
 *
 * The z-scale's whole job is that no two shell families share a band and the
 * brief's order (scene < windows < bars < werner < modal < toast) holds. A
 * comment can't enforce that; this test does. It is the durable guard the next
 * overlay author trips if they reintroduce an overlap.
 */
import { describe, expect, it } from "vitest";

import {
  WINDOW_Z_SPAN,
  Z_BANDS,
  assertInBand,
  assertNoSharedBands,
  clampWindowOffset,
  windowZIndex,
  zIndex,
  type ZFamily,
} from "./zScale";

describe("zScale — the documented shell z-scale (F-1 fix, F-2 guard)", () => {
  it("no two family bands overlap (assertNoSharedBands does not throw)", () => {
    expect(() => assertNoSharedBands()).not.toThrow();
  });

  it("the brief's paint order holds: scene < windows < bars < werner < modal < toast", () => {
    expect(Z_BANDS.scene.max).toBeLessThanOrEqual(Z_BANDS.windows.min);
    expect(Z_BANDS.windows.max).toBeLessThanOrEqual(Z_BANDS.bars.min);
    expect(Z_BANDS.bars.max).toBeLessThanOrEqual(Z_BANDS.launcher.min);
    expect(Z_BANDS.launcher.max).toBeLessThanOrEqual(Z_BANDS.werner.min);
    expect(Z_BANDS.werner.max).toBeLessThanOrEqual(Z_BANDS.modal.min);
    expect(Z_BANDS.modal.max).toBeLessThanOrEqual(Z_BANDS.menuOverModal.min);
    expect(Z_BANDS.menuOverModal.max).toBeLessThanOrEqual(Z_BANDS.ad.min);
    expect(Z_BANDS.ad.max).toBeLessThanOrEqual(Z_BANDS.toast.min);
  });

  it("the F-1 invariant: every window paints BELOW the bars on every tier", () => {
    // The defect was the mobile rail (z-40) outranking the windows layer (z-30)
    // AND tying WINDOW_Z_BASE (40). Now the entire windows band is strictly below
    // the bars band — so a window can never out-paint the nav rail, on any tier.
    expect(Z_BANDS.windows.max).toBeLessThanOrEqual(Z_BANDS.bars.min);
    expect(zIndex.windowsLayer).toBeLessThan(zIndex.bar);
    expect(zIndex.windowBase).toBeLessThan(zIndex.bar);
  });

  it("a window can never climb out of its band, for ANY stack offset", () => {
    for (const offset of [0, 1, 7, 18, 19, 100, 9999, -5, NaN]) {
      const z = windowZIndex(offset);
      expect(z).toBeGreaterThanOrEqual(Z_BANDS.windows.min);
      expect(z).toBeLessThan(Z_BANDS.windows.max);
      expect(z).toBeLessThan(zIndex.bar); // never reaches the bars
    }
  });

  it("clampWindowOffset stays within [0, WINDOW_Z_SPAN]", () => {
    expect(clampWindowOffset(-1)).toBe(0);
    expect(clampWindowOffset(0)).toBe(0);
    expect(clampWindowOffset(WINDOW_Z_SPAN)).toBe(WINDOW_Z_SPAN);
    expect(clampWindowOffset(WINDOW_Z_SPAN + 50)).toBe(WINDOW_Z_SPAN);
    expect(clampWindowOffset(NaN)).toBe(0);
  });

  it("every named zIndex value sits inside its declared family band", () => {
    const map: Record<keyof typeof zIndex, ZFamily> = {
      scene: "scene",
      windowsLayer: "windows",
      windowBase: "windows",
      bar: "bars",
      barFloating: "bars",
      launcher: "launcher",
      werner: "werner",
      wernerMascot: "werner",
      modal: "modal",
      menuOverModal: "menuOverModal",
      ad: "ad",
      toast: "toast",
    };
    for (const [name, family] of Object.entries(map) as [keyof typeof zIndex, ZFamily][]) {
      expect(() => assertInBand(family, zIndex[name])).not.toThrow();
    }
  });

  it("the SHIPPED assertNoSharedBands THROWS when a band is made to overlap (the guard bites)", () => {
    // Prove the REAL exported function bites, not a re-implemented copy: take a
    // COPY of the shipped Z_BANDS, push one family's floor down INTO its lower
    // neighbour so two real bands overlap, then feed that copy to the actual
    // assertNoSharedBands. (Z_BANDS itself is untouched — readonly + a fresh
    // object — so the production invariant is unaffected.)
    const overlapping: Record<string, { min: number; max: number }> = {};
    for (const [name, band] of Object.entries(Z_BANDS)) overlapping[name] = { ...band };
    // bars normally starts at 40 (== windows.max); drop it to 30 so it overlaps
    // the windows band [20,40) — the exact F-1 shape.
    overlapping.bars = { min: 30, max: 50 };

    expect(() => assertNoSharedBands(overlapping)).toThrow(/overlap/);
    // And the shipped, untouched scale still passes the same function.
    expect(() => assertNoSharedBands()).not.toThrow();
  });
});
