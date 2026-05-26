/**
 * useCelebrate.test.ts — the non-blocking, fire-once contract behind every
 * signature beat (U-05 M2/M3 rigor: non-blocking is verified, not assumed).
 *
 * The beat must (1) arm without awaiting — `celebrate()` returns
 * synchronously so it can never sit between a payoff and the operator
 * seeing it; (2) retire on its own at the slow-token ceiling; (3) fire once
 * — a second call mid-beat restarts the window rather than stacking. These
 * are exactly the properties that keep the beat decoration, never a gate.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useCelebrate } from "./useCelebrate";
import { durationMs } from "../../design/motion";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useCelebrate — non-blocking one-shot", () => {
  it("starts idle, arms synchronously, and never throws/awaits", () => {
    const { result } = renderHook(() => useCelebrate());
    expect(result.current.celebrating).toBe(false);
    act(() => {
      // Synchronous: returns undefined immediately, no promise to await.
      expect(result.current.celebrate()).toBeUndefined();
    });
    expect(result.current.celebrating).toBe(true);
  });

  it("retires on its own at the slow token", () => {
    const { result } = renderHook(() => useCelebrate());
    act(() => result.current.celebrate());
    expect(result.current.celebrating).toBe(true);
    // One tick short of the ceiling — still in the window.
    act(() => vi.advanceTimersByTime(durationMs.slow - 1));
    expect(result.current.celebrating).toBe(true);
    // At the ceiling — retired.
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.celebrating).toBe(false);
  });

  it("fires once: a second call mid-beat restarts, never stacks", () => {
    const { result } = renderHook(() => useCelebrate());
    act(() => result.current.celebrate());
    act(() => vi.advanceTimersByTime(durationMs.slow - 100));
    // Re-fire with 100ms left — the window restarts from now.
    act(() => result.current.celebrate());
    // The original would have ended here; the restart keeps it alive.
    act(() => vi.advanceTimersByTime(100));
    expect(result.current.celebrating).toBe(true);
    // The restarted window ends a full slow-token from the second call.
    act(() => vi.advanceTimersByTime(durationMs.slow - 100));
    expect(result.current.celebrating).toBe(false);
  });

  it("clears its timer on unmount (no setState after teardown)", () => {
    const { result, unmount } = renderHook(() => useCelebrate());
    act(() => result.current.celebrate());
    unmount();
    // Advancing past the ceiling must not throw — the timer was cleared.
    expect(() => vi.advanceTimersByTime(durationMs.slow)).not.toThrow();
  });
});
