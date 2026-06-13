/**
 * useSceneClock.phase.test.ts — SPR-06 M1: the deterministic time seam +
 * the continuous time-of-day phase scalar.
 *
 * Two contracts proven here, both ADDITIVE to the SPR-04 clock (the t/frame
 * degradation-ladder behaviour is still proven by useSceneClock.test.ts —
 * unmodified):
 *
 *   (a) phaseOf is a PURE, continuous, monotonic-within-a-day, wrapping scalar.
 *       We assert it at the load-bearing boundaries the spec names: the day
 *       wrap (23:59→00:00) and the dawn/noon/dusk/midnight anchors. No clock
 *       loop needed — phaseOf is exported precisely so the boundary maths is
 *       unit-testable in isolation.
 *
 *   (b) The INJECTABLE time source makes the phase byte-identical across runs:
 *       a fixed source → the same phase on every subscribe; the default (no
 *       injection) reads the wall clock. SPR-05's snapshot determinism depends
 *       on this seam — a fixed getTime pins the scene's light.
 *
 * We exercise phase through the imperative `subscribeSceneClock` (no React), the
 * same seam the canvas painters ride and the same one the SPR-04 tests use.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  subscribeSceneClock,
  phaseOf,
  wallClock,
  FROZEN_T,
} from "./useSceneClock";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Build an epoch-ms instant at a LOCAL h:m:s today (phaseOf reads local time,
 *  tracking the viewer's local day exactly as the OS prefers-color-scheme mood
 *  does). Using a Date constructor with local parts is timezone-agnostic for
 *  the assertion: we read back the same local components phaseOf uses. */
function localAt(h: number, m = 0, s = 0, ms = 0): number {
  const d = new Date();
  d.setHours(h, m, s, ms);
  return d.getTime();
}

describe("phaseOf — continuous time-of-day scalar (SPR-06 M1)", () => {
  it("anchors at the day quarters: midnight 0, dawn .25, noon .5, dusk .75", () => {
    expect(phaseOf(localAt(0, 0, 0))).toBeCloseTo(0, 6);
    expect(phaseOf(localAt(6, 0, 0))).toBeCloseTo(0.25, 6);
    expect(phaseOf(localAt(12, 0, 0))).toBeCloseTo(0.5, 6);
    expect(phaseOf(localAt(18, 0, 0))).toBeCloseTo(0.75, 6);
  });

  it("is monotonic increasing within a day (no backwards step between samples)", () => {
    let prev = -1;
    // Sample every 10 minutes across the whole day.
    for (let mins = 0; mins < 24 * 60; mins += 10) {
      const p = phaseOf(localAt(Math.floor(mins / 60), mins % 60, 0));
      expect(p).toBeGreaterThan(prev);
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThan(1);
      prev = p;
    }
  });

  it("WRAPS cleanly at the 23:59→00:00 boundary (0.999… → 0.0, not a backwards jump within the cycle)", () => {
    const lastMinute = phaseOf(localAt(23, 59, 59, 999));
    const firstInstant = phaseOf(localAt(0, 0, 0, 0));
    // 23:59:59.999 is essentially 1.0 from below…
    expect(lastMinute).toBeGreaterThan(0.999);
    expect(lastMinute).toBeLessThan(1);
    // …and the next day's first instant is exactly 0 — a single-cycle wrap, the
    // phase never reaches or exceeds 1.0 (which would read as a discontinuity).
    expect(firstInstant).toBe(0);
  });

  it("dawn/dusk EDGES read as expected (05:00 just before .25, 19:00 just after .75)", () => {
    expect(phaseOf(localAt(5, 0, 0))).toBeLessThan(0.25);
    expect(phaseOf(localAt(5, 0, 0))).toBeGreaterThan(0.2);
    expect(phaseOf(localAt(19, 0, 0))).toBeGreaterThan(0.75);
    expect(phaseOf(localAt(19, 0, 0))).toBeLessThan(0.8);
  });

  it("never returns >= 1 or < 0 across a fine sweep (the wrap invariant)", () => {
    for (let s = 0; s < 24 * 3600; s += 137) {
      const p = phaseOf(localAt(Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60));
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThan(1);
    }
  });
});

describe("subscribeSceneClock — injectable time source → deterministic phase (SPR-06 M1)", () => {
  it("a FIXED getTime → byte-identical phase across independent subscribes (SPR-05 snapshot determinism)", () => {
    const fixed = localAt(14, 30, 0); // a settled mid-afternoon instant
    const getTime = () => fixed;

    const a: number[] = [];
    const b: number[] = [];
    // Reduced-motion → exactly one frame each, phase sampled once, no loop.
    subscribeSceneClock((_t, _f, phase) => a.push(phase), { reducedMotion: true, getTime })();
    subscribeSceneClock((_t, _f, phase) => b.push(phase), { reducedMotion: true, getTime })();

    expect(a).toHaveLength(1);
    expect(a).toEqual(b); // byte-identical → the scene's light is pinned
    expect(a[0]).toBeCloseTo(phaseOf(fixed), 9);
  });

  it("under reduced-motion the phase is sampled exactly once (the frozen frame), never looped", () => {
    const raf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    const fixed = localAt(8, 0, 0);
    const frames: Array<[number, number, number]> = [];
    const stop = subscribeSceneClock(
      (t, f, phase) => frames.push([t, f, phase]),
      { reducedMotion: true, getTime: () => fixed },
    );
    expect(frames).toEqual([[FROZEN_T, 0, phaseOf(fixed)]]);
    expect(raf).not.toHaveBeenCalled();
    stop();
  });

  it("a RUNNING loop samples the (live) injected source each tick → continuous drift", () => {
    let cb: FrameRequestCallback | null = null;
    const raf = vi.fn((fn: FrameRequestCallback) => {
      cb = fn;
      return 1;
    });
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());

    // A source that advances 1 hour per call → the phase must DRIFT, not snap.
    let calls = 0;
    const base = localAt(0, 0, 0);
    const getTime = () => base + calls++ * 3_600_000;

    const phases: number[] = [];
    const stop = subscribeSceneClock((_t, _f, p) => phases.push(p), {
      reducedMotion: false,
      getTime,
    });
    cb!(0);
    cb!(16);
    cb!(32);
    // Three ticks → three DISTINCT, increasing phases (drift), not one snapped value.
    expect(phases).toHaveLength(3);
    expect(phases[1]).toBeGreaterThan(phases[0]);
    expect(phases[2]).toBeGreaterThan(phases[1]);
    stop();
  });

  it("the default (no injection) is the wall clock", () => {
    // wallClock is the exported production default; phaseOf(wallClock()) is the
    // current time-of-day. We only assert the seam exists + is in range (the
    // value is time-dependent, so we bound rather than pin it).
    const p = phaseOf(wallClock());
    expect(p).toBeGreaterThanOrEqual(0);
    expect(p).toBeLessThan(1);
  });
});
