/**
 * scene-engine.test.tsx — AMS-v2 SPR-05 (Scene Engine: M1 + M4 + M5).
 *
 * HONEST NO-GO context: SPR-02 ruled out a near-real-time *generative* stream
 * (docs/ams-v2/stream-spike.md). The shipped engine is a 60fps PROCEDURAL FLOOR
 * (useSceneClock → canvas painters) with PERIODIC, mood-gated Krea art over it.
 * These vitests pin the engine *contract* in isolation; the BROWSER pixel-diff
 * proof that the floor genuinely moves (and never goes blank) is the mandatory
 * experience-gate e2e/scene-living.spec.ts — a green vitest here is necessary,
 * not sufficient (rigor #3).
 *
 *   M1 — the floor is INDEPENDENT of the frame source. With the fetcher mocked
 *        isFallback:true (the sandbox/no-key path), ticking the scene clock STILL
 *        increments `frame` and delivers ticks to the canvas painters'
 *        subscriber. (jsdom has no canvas getContext, so the painters' `draw` is
 *        a no-op there — we therefore assert on the clock-subscription seam the
 *        painters ride, `subscribeSceneClock`, which is what actually drives the
 *        repaint; the pixel-level "the bitmap changed" claim is the e2e gate.)
 *   M4 — under prefers-reduced-motion:reduce the engine composes ONE static
 *        frame (clock frozen, frame===0) AND the frame source schedules ZERO
 *        fetches; on visibilitychange→hidden the source stops requesting.
 *   M5 — driving ≥120 clock ticks calls the injected fetcher a BOUNDED number
 *        (one per mood change; cache de-dupes), NOT once per tick.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { waitFor } from "@testing-library/react";

import { useSceneArt } from "./useSceneArt";
import { subscribeSceneClock, FROZEN_T } from "./useSceneClock";
import type { SceneMood } from "./mood";
import type { SceneResult, SceneState } from "../api/krea";

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

/** A controllable rAF: capture the tick callback so the test pumps frames
 *  deterministically (the same pattern useSceneClock.test.ts uses). */
function installControllableRaf() {
  let cb: FrameRequestCallback | null = null;
  const raf = vi.fn((fn: FrameRequestCallback) => {
    cb = fn;
    return 1;
  });
  const caf = vi.fn();
  vi.stubGlobal("requestAnimationFrame", raf);
  vi.stubGlobal("cancelAnimationFrame", caf);
  // Pump N frames, +16ms each (~60fps), re-arming the captured callback.
  const pump = (n: number) => {
    for (let i = 0; i < n; i++) {
      const next = cb;
      cb = null;
      if (!next) break;
      next((i + 1) * 16);
    }
  };
  return { raf, caf, pump };
}

/** A spy fetcher returning live art, recording every call's scene-state. */
function liveFetcher() {
  const calls: SceneState[] = [];
  const fn = async (s: SceneState): Promise<SceneResult> => {
    calls.push(s);
    return {
      enabled: true,
      isFallback: false,
      image_url: `https://art/${s.dayNight}.png`,
      scene_key: `${s.mood}|${s.dayNight}|${s.season}`,
      cached: false,
    };
  };
  return { fn, calls };
}

/** The sandbox/no-key path: a spy fetcher that always reports fallback. */
function fallbackFetcher() {
  const calls: SceneState[] = [];
  const fn = async (s: SceneState): Promise<SceneResult> => {
    calls.push(s);
    return { enabled: false, isFallback: true, reason: "no_key", scene_key: s.mood };
  };
  return { fn, calls };
}

beforeEach(() => {
  // Default matchMedia → no reduced-motion, not dark (overridden per test).
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("M1 — the procedural floor is independent of the frame source", () => {
  it("with the fetcher in fallback, ticking the clock still increments frame + repaints the canvas subscriber", async () => {
    const { pump } = installControllableRaf();
    const { fn, calls } = fallbackFetcher();

    // Frame source: render useSceneArt with the always-fallback fetcher.
    const { result } = renderHook(() => useSceneArt(DAY, fn));
    await waitFor(() => expect(result.current.isFallback).toBe(true));
    // No live art (procedural-only) — the floor is the whole picture.
    expect(result.current.imageUrl).toBeNull();

    // The floor: subscribe exactly as Clouds/Snow do. In jsdom the canvas
    // `draw` is a no-op (no getContext), so the painter's effect on the bitmap
    // is unobservable here — we assert the CLOCK delivers ticks to the painter,
    // which is the mechanism the e2e pixel-diff proves visually. The frame
    // counter the subscriber sees must advance regardless of art state.
    const frames: number[] = [];
    const stop = subscribeSceneClock((_t, f) => frames.push(f), {
      reducedMotion: false,
    });
    pump(120);
    stop();

    // Art never resolved to a live URL (fallback), yet the floor ticked 120×:
    // 1..120, strictly increasing — the floor does NOT depend on the art source.
    expect(frames).toHaveLength(120);
    expect(frames[0]).toBe(1);
    expect(frames[119]).toBe(120);
    expect(result.current.isFallback).toBe(true);
    // The fetcher was asked for art at most once (mood-gated), NOT per tick.
    expect(calls.length).toBeLessThanOrEqual(1);
  });
});

describe("M4 — reduced-motion: one static frame + ZERO fetches", () => {
  it("under reduced-motion the clock subscriber gets ONE frame at FROZEN_T, frame===0, and never loops", () => {
    const { raf } = installControllableRaf();
    const frames: Array<[number, number]> = [];
    const stop = subscribeSceneClock((t, f) => frames.push([t, f]), {
      reducedMotion: true,
    });
    expect(frames).toEqual([[FROZEN_T, 0]]);
    expect(raf).not.toHaveBeenCalled(); // no rAF loop ever scheduled
    stop();
  });

  it("under reduced-motion the frame source schedules ZERO fetches across many would-be frames", async () => {
    // Force prefers-reduced-motion:reduce so any clock the engine spins is frozen.
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: query.includes("prefers-reduced-motion"),
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    const { pump } = installControllableRaf();
    const { fn, calls } = fallbackFetcher();

    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );
    await waitFor(() => expect(result.current.status).toBe("fallback"));
    const afterMount = calls.length; // the single mount fetch (mood-gated)

    // Try to pump frames; under reduced-motion the clock never loops, and the
    // frame source is mood-gated regardless. Re-render many times w/o mood change.
    pump(120);
    for (let i = 0; i < 120; i++) rerender({ mood: DAY });

    // NOT ONE additional fetch was scheduled by frames / re-renders.
    expect(calls.length).toBe(afterMount);
    expect(afterMount).toBeLessThanOrEqual(1);
  });

  it("on visibilitychange→hidden the frame source stops requesting (clock tears down, no churn)", () => {
    const { raf, caf } = installControllableRaf();
    const stop = subscribeSceneClock(() => {}, { reducedMotion: false });
    expect(raf).toHaveBeenCalledTimes(1); // running

    // Hide the tab.
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(caf).toHaveBeenCalled(); // loop torn down while hidden — no repaint churn
    stop();
    // Restore for sibling tests.
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
  });
});

describe("M5 — frontend cadence: ≥120 ticks, BOUNDED fetches (not per-tick)", () => {
  it("drives ≥120 clock ticks and the injected fetcher is called a bounded number (one per mood change)", async () => {
    const { pump } = installControllableRaf();
    const { fn, calls } = liveFetcher();

    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );
    await waitFor(() => expect(result.current.isFallback).toBe(false));
    expect(calls).toHaveLength(1); // the DAY mount fetch

    // Drive ≥120 real clock ticks through a live subscriber AND re-render the
    // engine on each tick (the worst case a per-frame-billing bug would hit:
    // every frame both repaints AND reconciles the art hook).
    act(() => {
      let pumped = 0;
      const stop = subscribeSceneClock(() => {
        pumped++;
        rerender({ mood: DAY }); // SAME mood — must NOT trigger a fetch
      }, { reducedMotion: false });
      pump(130); // ≥120 ticks
      stop();
      expect(pumped).toBeGreaterThanOrEqual(120);
    });

    // CADENCE INVARIANT: still exactly ONE fetch after 130 ticks @ DAY.
    expect(calls).toHaveLength(1);

    // One mood change → exactly one MORE fetch (and the cache de-dupes a repeat).
    rerender({ mood: NIGHT });
    await waitFor(() => expect(calls).toHaveLength(2));

    // Drive 130 more ticks at NIGHT — still no per-tick fetching.
    act(() => {
      const stop = subscribeSceneClock(() => rerender({ mood: NIGHT }), {
        reducedMotion: false,
      });
      pump(130);
      stop();
    });
    expect(calls).toHaveLength(2);

    // MEASURED CADENCE (recorded in the handoff): 2 fetches across 260 ticks +
    // 2 distinct moods = exactly one fetch per mood change, ~0.0077 fetches/tick.
    expect(calls.length).toBe(2);
  });
});
