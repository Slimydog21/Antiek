/**
 * useSceneArt.test.tsx — SPR-04 milestone 4: the CADENCE invariant.
 *
 * THE assertion that protects the whole design: Krea is fetched ONLY on mood
 * change, NEVER per frame. We render useSceneArt with a spy fetcher, advance a
 * simulated clock by re-rendering many times WITHOUT changing the mood, and
 * assert the fetcher was called exactly once. Then we change the mood and
 * assert exactly one additional call. A refactor that wired the fetch to the
 * rAF clock would call it hundreds of times and redden this test.
 *
 * It also covers the degradation rung: a fallback fetch result → isFallback,
 * no live imageUrl (procedural-only).
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, renderHook } from "@testing-library/react";
import { waitFor } from "@testing-library/react";

import { useSceneArt } from "./useSceneArt";
import type { SceneMood } from "./mood";
import type { SceneResult, SceneState } from "../api/krea";

beforeAll(() => {
  if (!window.matchMedia) {
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
  }
});

afterEach(() => cleanup());

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

/** A fetcher that returns live art, recording every call. */
function liveFetcher(): { fn: (s: SceneState) => Promise<SceneResult>; calls: SceneState[] } {
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

describe("useSceneArt — Krea cadence", () => {
  it("fetches ONCE per mood, NOT per frame (re-renders don't refetch)", async () => {
    const { fn, calls } = liveFetcher();
    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );

    // Wait for the first resolve.
    await waitFor(() => expect(result.current.isFallback).toBe(false));
    expect(calls).toHaveLength(1);

    // Simulate MANY animation frames by re-rendering with the SAME mood. This
    // is what a per-frame bug would look like from React's perspective.
    for (let i = 0; i < 120; i++) {
      rerender({ mood: DAY });
    }
    // Still exactly one fetch — the cadence is mood-gated, not frame-gated.
    expect(calls).toHaveLength(1);
  });

  it("fetches again EXACTLY once when the mood changes", async () => {
    const { fn, calls } = liveFetcher();
    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );
    await waitFor(() => expect(result.current.isFallback).toBe(false));
    expect(calls).toHaveLength(1);

    rerender({ mood: NIGHT });
    await waitFor(() => expect(calls).toHaveLength(2));
    // The night scene-state was requested.
    expect(calls[1].dayNight).toBe("night");
  });

  it("a fallback fetch result → isFallback, no live imageUrl (procedural-only)", async () => {
    const calls: SceneState[] = [];
    const fn = async (s: SceneState): Promise<SceneResult> => {
      calls.push(s);
      return { enabled: false, isFallback: true, reason: "no_key", scene_key: null };
    };
    const { result } = renderHook(() => useSceneArt(DAY, fn));
    await waitFor(() => expect(result.current.status).toBe("fallback"));
    expect(result.current.isFallback).toBe(true);
    expect(result.current.imageUrl).toBeNull();
    expect(result.current.reason).toBe("no_key");
  });
});
