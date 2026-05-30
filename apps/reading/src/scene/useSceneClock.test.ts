/**
 * useSceneClock.test.ts — SPR-04 milestone 6: the degradation ladder rungs.
 *
 *   - reduced-motion → ONE static frame, NO rAF loop ever scheduled.
 *   - running        → the loop ticks (rAF scheduled), advancing t.
 *   - hidden tab     → the loop is torn down on visibilitychange; resumes on
 *                      show.
 *
 * We test the imperative `subscribeSceneClock` (the seam the canvas painters
 * use) because it has no React; the freeze/pause logic is identical to the
 * hook's. We stub rAF + document.hidden so the assertions are deterministic.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { subscribeSceneClock, FROZEN_T } from "./useSceneClock";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("subscribeSceneClock — reduced-motion freeze", () => {
  it("emits exactly ONE frame at FROZEN_T and schedules NO rAF loop", () => {
    const raf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);

    const frames: Array<[number, number]> = [];
    const stop = subscribeSceneClock((t, f) => frames.push([t, f]), {
      reducedMotion: true,
    });

    // One static composed frame, no loop.
    expect(frames).toEqual([[FROZEN_T, 0]]);
    // The decisive assertion: under reduced-motion we NEVER call rAF.
    expect(raf).not.toHaveBeenCalled();
    stop();
  });
});

describe("subscribeSceneClock — running loop", () => {
  it("schedules a rAF loop and advances t/frame when NOT reduced-motion", () => {
    // A controllable rAF: capture the callback so we can pump frames.
    let cb: FrameRequestCallback | null = null;
    const raf = vi.fn((fn: FrameRequestCallback) => {
      cb = fn;
      return 1;
    });
    const caf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);

    const frames: Array<[number, number]> = [];
    const stop = subscribeSceneClock((t, f) => frames.push([t, f]), {
      reducedMotion: false,
    });

    expect(raf).toHaveBeenCalledTimes(1); // the loop started
    // Pump three frames at +16ms each.
    cb!(0);
    cb!(16);
    cb!(32);
    expect(frames).toHaveLength(3);
    // t advances; frame counter increments 1,2,3.
    expect(frames[0][1]).toBe(1);
    expect(frames[2][1]).toBe(3);
    expect(frames[2][0]).toBeGreaterThan(frames[0][0]);
    stop();
    expect(caf).toHaveBeenCalled(); // loop torn down on teardown
  });
});

describe("subscribeSceneClock — visibility pause", () => {
  it("tears down the loop when the document becomes hidden, resumes when shown", () => {
    let cb: FrameRequestCallback | null = null;
    const raf = vi.fn((fn: FrameRequestCallback) => {
      cb = fn;
      return 1;
    });
    const caf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);

    const stop = subscribeSceneClock(() => {}, { reducedMotion: false });
    expect(raf).toHaveBeenCalledTimes(1);
    cb!(0); // one tick → schedules the next rAF
    const callsBeforeHide = raf.mock.calls.length;

    // Hide the tab.
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(caf).toHaveBeenCalled(); // loop cancelled while hidden

    // Show the tab → the loop restarts (a fresh rAF is scheduled).
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(raf.mock.calls.length).toBeGreaterThan(callsBeforeHide);

    stop();
  });
});
