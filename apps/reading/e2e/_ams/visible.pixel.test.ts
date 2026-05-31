/**
 * visible.pixel.test — unit calibration for the PURE pixel helpers behind
 * assertSceneVisible (SPR-01, milestone 3 / verification "Helper unit-calibration").
 *
 * The load-bearing assertion (rigor #3): feed `isSolidColor` a SYNTHETIC
 * solid-ice / solid-space frame and confirm it reports SOLID (true) — i.e.
 * assertSceneVisible would FAIL on an occluded/empty scene rather than pass
 * vacuously. Then confirm a synthetic gradient (a stand-in for the painted sky)
 * reports NOT solid, so a genuinely-visible scene passes.
 *
 * No browser here — these are the pure functions, so the calibration is fast
 * and deterministic and runs under vitest.
 */

import { describe, expect, it } from "vitest";
import { PNG } from "pngjs";

import {
  decodePng,
  regionVariance,
  distinctColors,
  isSolidColor,
  contrastRatio,
  relativeLuminance,
  SCENE_SOLID_VARIANCE_THRESHOLD,
  type Rgb,
} from "./visible";

/** Encode a solid-colour PNG of WxH. */
function solidPng(w: number, h: number, c: Rgb): Buffer {
  const png = new PNG({ width: w, height: h });
  for (let i = 0; i < w * h; i++) {
    const o = i * 4;
    png.data[o] = c.r;
    png.data[o + 1] = c.g;
    png.data[o + 2] = c.b;
    png.data[o + 3] = 255;
  }
  return PNG.sync.write(png);
}

/** Encode a vertical gradient PNG — a stand-in for the procedural sky. */
function gradientPng(w: number, h: number, top: Rgb, bottom: Rgb): Buffer {
  const png = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) {
    const t = y / Math.max(1, h - 1);
    const r = Math.round(top.r + (bottom.r - top.r) * t);
    const g = Math.round(top.g + (bottom.g - top.g) * t);
    const b = Math.round(top.b + (bottom.b - top.b) * t);
    for (let x = 0; x < w; x++) {
      const o = (y * w + x) * 4;
      png.data[o] = r;
      png.data[o + 1] = g;
      png.data[o + 2] = b;
      png.data[o + 3] = 255;
    }
  }
  return PNG.sync.write(png);
}

// The actual ice/space fills the occluding route body uses (bg-ice-2 / bg-space-2).
const ICE: Rgb = { r: 0xe8, g: 0xee, b: 0xf4 }; // a light ice
const SPACE: Rgb = { r: 0x12, g: 0x16, b: 0x22 }; // a dark space

describe("decodePng", () => {
  it("round-trips a solid buffer to RGBA pixels", () => {
    const img = decodePng(solidPng(8, 8, ICE));
    expect(img.width).toBe(8);
    expect(img.height).toBe(8);
    expect(img.data.length).toBe(8 * 8 * 4);
    expect(img.data[0]).toBe(ICE.r);
  });
});

describe("isSolidColor — the calibration that makes assertSceneVisible honest", () => {
  it("reports SOLID on a solid-ice frame (assertSceneVisible would FAIL here)", () => {
    const img = decodePng(solidPng(120, 60, ICE));
    expect(regionVariance(img)).toBeLessThan(SCENE_SOLID_VARIANCE_THRESHOLD);
    expect(distinctColors(img)).toBeLessThanOrEqual(2);
    expect(isSolidColor(img)).toBe(true);
  });

  it("reports SOLID on a solid-space (dark) frame too", () => {
    const img = decodePng(solidPng(120, 60, SPACE));
    expect(isSolidColor(img)).toBe(true);
  });

  it("reports NOT solid on a sky-like gradient (a visible scene passes)", () => {
    const img = decodePng(gradientPng(120, 60, { r: 90, g: 130, b: 200 }, { r: 230, g: 200, b: 150 }));
    expect(regionVariance(img)).toBeGreaterThan(SCENE_SOLID_VARIANCE_THRESHOLD);
    expect(distinctColors(img)).toBeGreaterThan(4);
    expect(isSolidColor(img)).toBe(false);
  });

  it("a 1-pixel of noise on an otherwise flat fill is still SOLID (variance AND distinct both gate)", () => {
    // Guards against a single stray antialiased pixel flipping a truly-flat
    // occluded body into a false 'visible'.
    const png = new PNG({ width: 100, height: 50 });
    for (let i = 0; i < 100 * 50; i++) {
      const o = i * 4;
      png.data[o] = ICE.r;
      png.data[o + 1] = ICE.g;
      png.data[o + 2] = ICE.b;
      png.data[o + 3] = 255;
    }
    // one off-colour pixel
    png.data[0] = 0;
    png.data[1] = 0;
    png.data[2] = 0;
    const img = decodePng(PNG.sync.write(png));
    expect(isSolidColor(img)).toBe(true);
  });
});

describe("contrast helpers", () => {
  it("black-on-white is the max ratio (~21)", () => {
    expect(contrastRatio({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 })).toBeCloseTo(21, 0);
  });
  it("same colour is ratio 1", () => {
    expect(contrastRatio({ r: 100, g: 100, b: 100 }, { r: 100, g: 100, b: 100 })).toBeCloseTo(1, 5);
  });
  it("relative luminance is monotonic in brightness", () => {
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeLessThan(relativeLuminance({ r: 255, g: 255, b: 255 }));
  });
});
