/**
 * WERNER station compat matrix — the cursor-as-bait read seam.
 *
 * Post-2026-07-02 fixed-station rework: Werner no longer chases the cursor, so
 * the old reel/lag/roam scenarios (REEL_TAU_MS, ROAM_* constants, the lagged
 * pursuit target, centerLaggedTarget, reelStep) are gone with the reel. What
 * REMAINS load-bearing is the read seam the bait + line + station gag consume:
 * the flag gate, the reduced-motion freeze, tab-hidden, pointer-idle (the gag
 * gate), and the live cursor position (the bait IS the cursor). See
 * docs/htmlspec/werner-fixed-station/DESIGN.md.
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
  POINTER_IDLE_MS,
  SAMPLE_INTERVAL_MS,
  useMouseFollow,
  wernerIceFishingCursor,
} from "../werner";

describe("WERNER station compat matrix (cursor-as-bait)", () => {
  it("1 · ice flag default on unless VITE_WERNER_ICE_FISHING=0", () => {
    // The flag still gates the bait overlay, the fishing line, and the station
    // gag — it just no longer gates a reel (there is none).
    expect(wernerIceFishingCursor).toBe(true);
  });

  it("2 · reduced motion → frozen read seam (no live, no target, no follow)", () => {
    const now = () => 0;
    const { result } = renderHook(() => useMouseFollow({ now, disabled: true }));
    expect(result.current.read().live).toBeNull();
    expect(result.current.read().target).toBeNull();
  });

  it("3 · tab hidden → tabHidden true (bait + line hide)", () => {
    withFakeTimers(() => {
      const now = () => 0;
      const { result } = renderHook(() => useMouseFollow({ now }));
      Object.defineProperty(document, "hidden", { value: true, configurable: true });
      act(() => document.dispatchEvent(new Event("visibilitychange")));
      expect(result.current.read().tabHidden).toBe(true);
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
    });
  });

  it("4 · pointer idle after POINTER_IDLE_MS (the station gag gate flips on)", () => {
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
      // Pointer idle ⇒ the own-hole gag owns Werner and the cursor-line hides.
      expect(result.current.read().pointerIdle).toBe(true);
    });
  });

  it("5 · the cursor IS the bait — live tracks the live pointer position", () => {
    withFakeTimers(() => {
      let t = 0;
      const now = () => t;
      const { result } = renderHook(() => useMouseFollow({ now }));
      act(() => {
        document.dispatchEvent(
          new PointerEvent("pointermove", { clientX: 800, clientY: 600, bubbles: true }),
        );
      });
      // `live` is exactly where the mouse is — the bait worm rides it, and the
      // fishing line's free end lands there. No lag on the bait itself.
      expect(result.current.read().live).toEqual({ x: 800, y: 600 });
    });
  });

  it("6 · a fresh pointer move is NOT idle (the cursor-line shows, gag stands down)", () => {
    withFakeTimers(() => {
      let t = 0;
      const now = () => t;
      const { result } = renderHook(() => useMouseFollow({ now }));
      act(() => {
        document.dispatchEvent(
          new PointerEvent("pointermove", { clientX: 42, clientY: 42, bubbles: true }),
        );
        // A short advance, well under POINTER_IDLE_MS.
        t += SAMPLE_INTERVAL_MS;
        vi.advanceTimersByTime(SAMPLE_INTERVAL_MS);
      });
      expect(result.current.read().pointerIdle).toBe(false);
    });
  });

  it("7 · WernerStage factory exports (choreography seam intact)", async () => {
    const { createWernerStage } = await import("../werner/WernerStage");
    expect(typeof createWernerStage).toBe("function");
  });
});
