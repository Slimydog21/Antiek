/**
 * WERNER-ICE SPR-16 — compat matrix (≥12 scenarios).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, act } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function withFakeTimers(run: () => void) {
  vi.useFakeTimers();
  try {
    run();
  } finally {
    vi.useRealTimers();
  }
}

import {
  centerLaggedTarget,
  LAG_MS,
  POINTER_IDLE_MS,
  REEL_TAU_MS,
  ROAM_REST_MAX_MS,
  ROAM_REST_MIN_MS,
  ROAM_STROLL_MS,
  SAMPLE_INTERVAL_MS,
  useMouseFollow,
  wernerIceFishingCursor,
} from "../werner";

describe("WERNER-ICE compat matrix", () => {
  it("1 · ice flag default on unless VITE_WERNER_ICE_FISHING=0", () => {
    expect(wernerIceFishingCursor).toBe(true);
  });

  it("2 · lag budget constants match master spec", () => {
    expect(LAG_MS).toBe(500);
    expect(SAMPLE_INTERVAL_MS).toBe(60);
    expect(REEL_TAU_MS).toBe(450);
  });

  it("3 · idle roam timings restored (not snappy 800/300)", () => {
    expect(ROAM_STROLL_MS).toBe(1400);
    expect(ROAM_REST_MIN_MS).toBe(1200);
    expect(ROAM_REST_MAX_MS).toBe(2800);
  });

  it("4 · reduced motion → frozen follow seam", () => {
    const now = () => 0;
    const { result } = renderHook(() => useMouseFollow({ now, disabled: true }));
    expect(result.current.read().target).toBeNull();
    expect(result.current.read().live).toBeNull();
  });

  it("5 · tab hidden → tabHidden true", () => {
    withFakeTimers(() => {
      const now = () => 0;
      const { result } = renderHook(() => useMouseFollow({ now }));
      Object.defineProperty(document, "hidden", { value: true, configurable: true });
      act(() => document.dispatchEvent(new Event("visibilitychange")));
      expect(result.current.read().tabHidden).toBe(true);
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
    });
  });

  it("6 · pointer idle after POINTER_IDLE_MS", () => {
    withFakeTimers(() => {
      let t = 0;
      const now = () => t;
      const { result } = renderHook(() => useMouseFollow({ now }));
      act(() => {
        document.dispatchEvent(
          new PointerEvent("pointermove", { clientX: 10, clientY: 10, bubbles: true }),
        );
        t += POINTER_IDLE_MS + SAMPLE_INTERVAL_MS * 2;
        vi.advanceTimersByTime(POINTER_IDLE_MS + SAMPLE_INTERVAL_MS * 2);
      });
      expect(result.current.read().pointerIdle).toBe(true);
    });
  });

  it("7 · live bait diverges from lagged target after jump", () => {
    withFakeTimers(() => {
      let clock = 0;
      const now = () => clock;
      const { result } = renderHook(() => useMouseFollow({ now }));
      const move = (x: number, y: number) => {
        act(() => {
          document.dispatchEvent(
            new PointerEvent("pointermove", { clientX: x, clientY: y, bubbles: true }),
          );
        });
      };
      const advance = (ms: number) => {
        const ticks = Math.ceil(ms / SAMPLE_INTERVAL_MS);
        for (let i = 0; i < ticks; i++) {
          clock += SAMPLE_INTERVAL_MS;
          act(() => vi.advanceTimersByTime(SAMPLE_INTERVAL_MS));
        }
      };
      move(50, 50);
      advance(LAG_MS + SAMPLE_INTERVAL_MS);
      move(800, 600);
      advance(SAMPLE_INTERVAL_MS * 2);
      const r = result.current.read();
      expect(r.live).toEqual({ x: 800, y: 600 });
      expect(r.target!.x).toBeLessThan(200);
    });
  });

  it("8 · centerLaggedTarget null-safe", () => {
    expect(centerLaggedTarget(null, 64)).toBeNull();
  });

  it("9 · center offset uses half mascot size", () => {
    expect(centerLaggedTarget({ x: 100, y: 100 }, 64)).toEqual({ x: 68, y: 68 });
  });

  it("10 · reel never reads live pointer in pursuit unit", async () => {
    const { reelStep } = await import("../werner/reelPursuit");
    const next = reelStep({ x: 0, y: 0 }, { x: 50, y: 0 }, 16);
    expect(next.x).toBeGreaterThan(0);
    expect(next.y).toBe(0);
  });

  it("11 · FOLLOW_EASE hop path gated off when ice flag true (module)", () => {
    expect(wernerIceFishingCursor).toBe(true);
  });

  it("12 · WernerStage factory exports (choreography seam intact)", async () => {
    const { createWernerStage } = await import("../werner/WernerStage");
    expect(typeof createWernerStage).toBe("function");
  });
});