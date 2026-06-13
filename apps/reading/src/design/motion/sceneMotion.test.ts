/**
 * sceneMotion.test.ts — the scene motion vocabulary's INVARIANTS (ALC SPR-06 M2).
 *
 * The tokens carry rationale in comments; these tests pin the load-bearing
 * RELATIONSHIPS between them — the things that would silently break the design
 * if a future edit nudged a number without re-reading the rationale:
 *
 *   • the ambient breath must never out-travel the deliberate pointer parallax
 *     (DRIFT.maxAmplitudePx < PARALLAX.pointerMaxPx) — ambient < interactive;
 *   • the drift periods must be mutually PRIME (and x/y disjoint) so the
 *     composition never visibly loops;
 *   • the crossfade + light durations are coupled (choreography reads as one
 *     event), and the reduced-motion forms are near-instant;
 *   • the painted-opacity ceiling leaves headroom for the procedural floor.
 */
import { describe, expect, it } from "vitest";

import {
  CROSSFADE,
  LIGHT,
  DRIFT,
  PARALLAX,
  PENGUIN,
  sceneDurationMs,
} from "./sceneMotion";

/** Trial-division primality (period seconds are small). */
function isPrime(n: number): boolean {
  if (n < 2) return false;
  for (let i = 2; i * i <= n; i++) if (n % i === 0) return false;
  return true;
}

describe("DRIFT — the breath stays under the deliberate pointer parallax", () => {
  it("ambient breath amplitude < interactive pointer cap (ambient must never out-shout a pointer move)", () => {
    expect(DRIFT.maxAmplitudePx).toBeLessThan(PARALLAX.pointerMaxPx);
    // The vertical breath is the subtlest component (vertical motion reads more).
    expect(DRIFT.maxAmplitudeYPx).toBeLessThan(DRIFT.maxAmplitudePx);
  });

  it("reduced-motion amplitude is exactly 0 (the breath stops; static pose IS the reduced state)", () => {
    expect(DRIFT.reducedAmplitudePx).toBe(0);
  });
});

describe("DRIFT — periods are mutually prime so the composition never visibly loops", () => {
  it("every x-period (in whole seconds) is prime", () => {
    for (const ms of DRIFT.periodsMs) {
      const secs = ms / 1000;
      expect(Number.isInteger(secs)).toBe(true);
      expect(isPrime(secs)).toBe(true);
    }
  });

  it("every y-period (in whole seconds) is prime", () => {
    for (const ms of DRIFT.periodsYMs) {
      const secs = ms / 1000;
      expect(Number.isInteger(secs)).toBe(true);
      expect(isPrime(secs)).toBe(true);
    }
  });

  it("x and y period sets are DISJOINT (so each plane's breath traces a non-repeating Lissajous, not a diagonal)", () => {
    const x = new Set(DRIFT.periodsMs);
    for (const y of DRIFT.periodsYMs) expect(x.has(y)).toBe(false);
  });

  it("there are exactly 3 planes' worth of periods (index-aligned with Mountainscape PLANES)", () => {
    expect(DRIFT.periodsMs).toHaveLength(3);
    expect(DRIFT.periodsYMs).toHaveLength(3);
  });

  it("periods are weather-slow (tens of seconds, far beyond the interaction ceiling)", () => {
    for (const ms of [...DRIFT.periodsMs, ...DRIFT.periodsYMs]) {
      expect(ms).toBeGreaterThanOrEqual(20_000); // ≥ 20s — ambient, not a button
    }
  });
});

describe("CROSSFADE + LIGHT — coupled choreography, near-instant under reduced-motion", () => {
  it("light shares the crossfade duration (the two read as ONE event)", () => {
    expect(LIGHT.ms).toBe(CROSSFADE.ms);
  });

  it("the crossfade is slower than the interaction ceiling (a sky is a bigger, calmer event than a control)", () => {
    expect(sceneDurationMs.crossfade).toBeGreaterThan(800); // > the `slow` token
  });

  it("reduced-motion crossfade is present but near-instant (a dissolve, not a hard cut)", () => {
    expect(sceneDurationMs.crossfadeReduced).toBeLessThanOrEqual(1);
    expect(sceneDurationMs.crossfadeReduced).toBeGreaterThan(0); // still a transition
  });

  it("painted opacity leaves headroom so the procedural snow/cloud floor reads on top", () => {
    expect(CROSSFADE.paintedOpacity).toBeGreaterThan(0);
    expect(CROSSFADE.paintedOpacity).toBeLessThan(1); // art tints, never fully occludes
  });
});

describe("PENGUIN — scenery timings are named (not inline literals)", () => {
  it("exposes journey + bob durations and easings", () => {
    expect(PENGUIN.journeyDuration).toMatch(/^\d/);
    expect(PENGUIN.bobDuration).toMatch(/^\d/);
    expect(PENGUIN.journeyEase).toBe("linear");
    expect(PENGUIN.bobEase).toBe("ease-in-out");
  });
});
