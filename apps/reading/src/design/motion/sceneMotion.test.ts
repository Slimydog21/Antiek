import { describe, expect, it } from "vitest";

import {
  CROSSFADE,
  DRIFT,
  crossfadeMaxSlopePerMs,
  crossfadeOpacity,
  createCrossfadeTransition,
  retargetCrossfade,
  sceneLayerTransform,
  sceneParallaxPx,
} from "./sceneMotion";

describe("sceneLayerTransform", () => {
  it("drifts each layer from pure scene-clock input", () => {
    expect(sceneLayerTransform("peaks", 12_345)).toMatchInlineSnapshot(`
      {
        "opacity": 1,
        "x": 2.2774,
        "y": -0.0954,
      }
    `);
    expect(sceneLayerTransform("clouds", 12_345)).toMatchInlineSnapshot(`
      {
        "opacity": 1,
        "x": 9.9425,
        "y": 0.38,
      }
    `);
    expect(sceneLayerTransform("snow", 12_345)).toMatchInlineSnapshot(`
      {
        "opacity": 1,
        "x": 2.3871,
        "y": -1.0034,
      }
    `);
  });

  it("collapses drift to the static pose under reduced-motion", () => {
    expect(sceneLayerTransform("clouds", 12_345, { reducedMotion: true })).toEqual({
      x: 0,
      y: 0,
      opacity: 1,
    });
  });
});

describe("sceneParallaxPx", () => {
  it("scales parallax by layer coefficient", () => {
    expect(sceneParallaxPx("peaks", { x: 0.5, y: -1 }, 8)).toEqual({
      x: 1.12,
      y: -2.24,
    });
    expect(sceneParallaxPx("snow", { x: 0.5, y: -1 }, 8)).toEqual({
      x: 2.72,
      y: -5.44,
    });
  });

  it("collapses parallax under reduced-motion", () => {
    expect(sceneParallaxPx("snow", { x: 1, y: 1 }, 8, { reducedMotion: true })).toEqual({
      x: 0,
      y: 0,
    });
  });
});

describe("interruptible crossfade envelope", () => {
  it("fades toward the painted opacity ceiling", () => {
    const fade = createCrossfadeTransition(1000);
    expect(crossfadeOpacity(fade, 1000)).toBe(0);
    expect(crossfadeOpacity(fade, 1600)).toBeCloseTo(CROSSFADE.paintedOpacity / 2, 5);
    expect(crossfadeOpacity(fade, 2200)).toBe(CROSSFADE.paintedOpacity);
  });

  it("retargets from current opacity when interrupted, never snapping to zero", () => {
    const first = createCrossfadeTransition(0);
    const interruptAt = 480;
    const opacityAtInterrupt = crossfadeOpacity(first, interruptAt);
    const second = retargetCrossfade(first, interruptAt, 0.2);

    expect(second.fromOpacity).toBe(opacityAtInterrupt);
    expect(crossfadeOpacity(second, interruptAt)).toBe(opacityAtInterrupt);
    expect(crossfadeOpacity(second, interruptAt + 1)).toBeCloseTo(opacityAtInterrupt, 4);
  });

  it("keeps interruption continuity within the envelope's max slope", () => {
    const first = createCrossfadeTransition(0);
    const interruptAt = 777;
    const second = retargetCrossfade(first, interruptAt, CROSSFADE.paintedOpacity);
    const before = crossfadeOpacity(first, interruptAt - 1);
    const at = crossfadeOpacity(second, interruptAt);
    const allowed = crossfadeMaxSlopePerMs(first) + 0.002;

    expect(Math.abs(at - before)).toBeLessThanOrEqual(allowed);
  });

  it("uses instant cuts under reduced-motion", () => {
    const fade = createCrossfadeTransition(0, { reducedMotion: true });
    expect(fade.durationMs).toBe(0);
    expect(crossfadeOpacity(fade, 0)).toBe(CROSSFADE.paintedOpacity);
    expect(retargetCrossfade(fade, 250, 0.1, { reducedMotion: true })).toEqual({
      fromOpacity: 0.1,
      toOpacity: 0.1,
      startedAtMs: 250,
      durationMs: 0,
    });
  });

  it("keeps drift periods deterministic and pairwise distinct", () => {
    const periods = Object.values(DRIFT).flatMap((v) => [v.xPeriodMs, v.yPeriodMs]);
    expect(new Set(periods).size).toBe(periods.length);
    for (const period of periods) expect(period).toBeGreaterThan(30_000);
  });
});
