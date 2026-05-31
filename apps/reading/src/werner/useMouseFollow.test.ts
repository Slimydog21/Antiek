/**
 * useMouseFollow.test.ts — the ~5s-lagged cursor pursuit (SPR-05).
 *
 * Deterministic: a FAKE CLOCK (injected `now`) advanced in lockstep with
 * vitest's fake `setInterval`, plus synthetic `pointermove` events. No real
 * time, no real mouse. Load-bearing claims:
 *  - the target trails the cursor by ~LAG_MS (where the mouse WAS 5s ago,
 *    not where it is now);
 *  - cold start (< 5s of history) falls back to the oldest sample (the lag
 *    ramps up — an honest approximation);
 *  - a still pointer past POINTER_IDLE_MS reports pointerIdle (caller wanders);
 *  - reduced-motion (disabled) returns a frozen null target with NO listeners
 *    and NO sampling work;
 *  - sampling pauses when the tab is hidden (no background work).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  LAG_MS,
  POINTER_IDLE_MS,
  SAMPLE_INTERVAL_MS,
  useMouseFollow,
} from "./useMouseFollow";

// A fake clock the test drives by hand, fed to the hook as `now` AND used to
// keep vitest's fake-timer setInterval in step. We advance in WHOLE sample
// intervals so the manual clock and the faked setInterval never desync (a
// partial step would move the clock without firing a tick, skewing the lag).
let clock = 0;
const now = () => clock;
/** Advance `ticks` whole sample intervals (the deterministic unit). */
function advanceTicks(ticks: number) {
  for (let i = 0; i < ticks; i++) {
    clock += SAMPLE_INTERVAL_MS;
    act(() => {
      vi.advanceTimersByTime(SAMPLE_INTERVAL_MS);
    });
  }
}
/** Whole ticks that span at least `ms`. */
function ticksFor(ms: number) {
  return Math.ceil(ms / SAMPLE_INTERVAL_MS);
}
function advance(ms: number) {
  advanceTicks(ticksFor(ms));
}

function movePointer(x: number, y: number) {
  act(() => {
    window.dispatchEvent(
      new MouseEvent("pointermove", { clientX: x, clientY: y }),
    );
  });
}

beforeEach(() => {
  clock = 0;
  vi.useFakeTimers();
  // Default: tab visible.
  Object.defineProperty(document, "hidden", { value: false, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useMouseFollow", () => {
  it("trails the cursor by ~LAG_MS (returns where the mouse WAS, not where it is)", () => {
    const { result } = renderHook(() => useMouseFollow({ now }));

    // The mouse sits at A for a full LAG window, then jumps to B.
    movePointer(100, 100);
    advance(LAG_MS + SAMPLE_INTERVAL_MS); // build >5s of history at A
    movePointer(900, 700);
    advance(SAMPLE_INTERVAL_MS * 4); // a beat at B, but < 5s

    const reading = result.current.read();
    expect(reading.target).not.toBeNull();
    // The lagged target is still near A (~5s ago), NOT the live B.
    expect(reading.target!.x).toBeLessThan(300);
    expect(reading.target!.y).toBeLessThan(300);
    expect(reading.pointerIdle).toBe(false); // just moved to B
  });

  it("eventually catches up to B after another LAG window elapses", () => {
    const { result } = renderHook(() => useMouseFollow({ now }));
    movePointer(100, 100);
    advance(LAG_MS + SAMPLE_INTERVAL_MS);
    movePointer(900, 700);
    // Let the full lag window pass with the pointer parked at B.
    advance(LAG_MS + SAMPLE_INTERVAL_MS);
    const reading = result.current.read();
    // Now the 5s-old point IS B.
    expect(reading.target!.x).toBeGreaterThan(700);
    expect(reading.target!.y).toBeGreaterThan(500);
  });

  it("cold start (< 5s of history) falls back to the oldest sample (lag ramps up)", () => {
    const { result } = renderHook(() => useMouseFollow({ now }));
    movePointer(400, 300);
    advance(SAMPLE_INTERVAL_MS * 3); // only ~360ms of history, far under LAG_MS
    const reading = result.current.read();
    // No 5s-old sample exists yet → use the oldest we have (≈ the first move).
    expect(reading.target).not.toBeNull();
    expect(reading.target!.x).toBe(400);
    expect(reading.target!.y).toBe(300);
  });

  it("reports pointerIdle once the pointer is still past POINTER_IDLE_MS", () => {
    const { result } = renderHook(() => useMouseFollow({ now }));
    movePointer(200, 200);
    advance(SAMPLE_INTERVAL_MS * 2);
    expect(result.current.read().pointerIdle).toBe(false);
    // Sit still well past the idle threshold.
    advance(POINTER_IDLE_MS + SAMPLE_INTERVAL_MS);
    expect(result.current.read().pointerIdle).toBe(true);
    // A move resumes active follow immediately.
    movePointer(500, 500);
    expect(result.current.read().pointerIdle).toBe(false);
  });

  it("reduced motion (disabled) → frozen null target, no listeners installed", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const { result } = renderHook(() => useMouseFollow({ now, disabled: true }));
    // No pointermove listener installed (zero involuntary follow).
    const installedPointerMove = addSpy.mock.calls.some(
      (c) => c[0] === "pointermove",
    );
    expect(installedPointerMove).toBe(false);
    movePointer(300, 300);
    advance(LAG_MS * 2);
    const reading = result.current.read();
    expect(reading.target).toBeNull();
    expect(reading.pointerIdle).toBe(true);
    addSpy.mockRestore();
  });

  it("pauses sampling when the tab is hidden (no background work)", () => {
    const { result } = renderHook(() => useMouseFollow({ now }));
    movePointer(150, 150);
    advance(SAMPLE_INTERVAL_MS * 2);
    const before = result.current.read().target;
    expect(before).not.toBeNull();
    // Hide the tab → the interval should stop ticking new samples.
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    // Move + advance while hidden; the lagged target must not gain NEW history
    // (sampling is paused) — the most recent sample stays the last visible one.
    movePointer(800, 800);
    advance(LAG_MS);
    const after = result.current.read().target;
    // Still pointing at (or before) the pre-hide region, not the hidden move.
    expect(after!.x).toBeLessThan(400);
  });
});
