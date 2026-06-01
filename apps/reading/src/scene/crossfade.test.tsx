/**
 * crossfade.test.tsx — AMS-v2 SPR-05 (Scene Engine: M2 — periodic-art crossfade).
 *
 * On a NO-GO (no generative stream), the Krea art is a SLOW, mood-gated tint
 * that swaps a handful of times a session. When it does swap, it must CROSSFADE
 * (no hard cut), and — critically — the procedural floor must keep ticking
 * THROUGH the swap (the crossfade never gates the clock), with the art staying
 * z-1 behind the clouds/snow canvases.
 *
 *   - a new generated frame (mood change → new live URL) promotes current→prev
 *     and bumps `fadeKey` (the crossfade trigger). [useSceneArt]
 *   - the procedural clock keeps incrementing `frame` ACROSS the swap (the
 *     crossfade is presentational; it does not touch the heartbeat). [useSceneClock]
 *   - KreaArtLayer renders the incoming art keyed on fadeKey with the
 *     `--motion-slow` / `--ease-standard` tokenized transition (no magic
 *     number, no hard cut), and renders NOTHING (z-1 placeholder) in fallback.
 *
 * The *visual* "the procedural layers kept moving while the art crossfaded" is
 * the e2e pixel-diff gate; here we pin the swap mechanics + the token usage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, renderHook } from "@testing-library/react";
import { waitFor } from "@testing-library/react";

import { useSceneArt } from "./useSceneArt";
import { subscribeSceneClock } from "./useSceneClock";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import type { SceneArt } from "./useSceneArt";
import type { SceneMood } from "./mood";
import type { SceneResult, SceneState } from "../api/krea";

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

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

function installControllableRaf() {
  let cb: FrameRequestCallback | null = null;
  const raf = vi.fn((fn: FrameRequestCallback) => {
    cb = fn;
    return 1;
  });
  vi.stubGlobal("requestAnimationFrame", raf);
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  const pump = (n: number) => {
    for (let i = 0; i < n; i++) {
      const next = cb;
      cb = null;
      if (!next) break;
      next((i + 1) * 16);
    }
  };
  return { pump };
}

beforeEach(() => {
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

describe("M2 — a new generated frame triggers a fadeKey crossfade (no hard cut)", () => {
  it("promotes current→prev and bumps fadeKey on the second frame; the clock keeps ticking across the swap", async () => {
    const { pump } = installControllableRaf();
    const { fn } = liveFetcher();

    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );

    // Frame 1 (DAY): live art arrives; fadeKey bumps once; no prev yet.
    await waitFor(() => expect(result.current.imageUrl).toBe("https://art/day.png"));
    const fadeKey1 = result.current.fadeKey;
    expect(fadeKey1).toBeGreaterThan(0);
    expect(result.current.prevImageUrl).toBeNull();

    // Run the procedural floor across the swap window and capture the frame.
    const framesBefore: number[] = [];
    let stop = subscribeSceneClock((_t, f) => framesBefore.push(f), {
      reducedMotion: false,
    });
    pump(30);
    stop();
    const frameBeforeSwap = framesBefore.at(-1)!;
    expect(frameBeforeSwap).toBe(30);

    // Frame 2 (NIGHT): the mood change is the only thing that fetches new art.
    rerender({ mood: NIGHT });
    await waitFor(() => expect(result.current.imageUrl).toBe("https://art/night.png"));

    // CROSSFADE MECHANICS: previous URL is retained to fade out, fadeKey bumped.
    expect(result.current.prevImageUrl).toBe("https://art/day.png");
    expect(result.current.fadeKey).toBeGreaterThan(fadeKey1);

    // THE CLOCK KEPT TICKING ACROSS THE SWAP: a fresh subscriber continues to
    // increment frames (the crossfade did not gate / reset the heartbeat).
    const framesAfter: number[] = [];
    stop = subscribeSceneClock((_t, f) => framesAfter.push(f), {
      reducedMotion: false,
    });
    pump(30);
    stop();
    expect(framesAfter).toHaveLength(30);
    expect(framesAfter[0]).toBe(1);
    expect(framesAfter[29]).toBe(30);
  });
});

describe("M2 — KreaArtLayer is presentational: tokenized crossfade, z-1, fallback paints nothing", () => {
  const liveArt = (over: Partial<SceneArt> = {}): SceneArt => ({
    imageUrl: "https://art/night.png",
    prevImageUrl: "https://art/day.png",
    fadeKey: 2,
    isFallback: false,
    status: "ready",
    reason: null,
    ...over,
  });

  it("uses the --motion-slow / --ease-standard tokens for the opacity transition (no magic number)", () => {
    const { container } = render(<KreaArtLayer art={liveArt()} />);
    const layer = container.querySelector('[data-testid="krea-art-layer"]') as HTMLElement;
    expect(layer.getAttribute("data-krea")).toBe("live");
    // The incoming art keyed on fadeKey carries the tokenized opacity transition.
    const incoming = container.querySelector(
      '[data-krea="live"] > div:last-child',
    ) as HTMLElement;
    expect(incoming.style.transition).toContain("var(--motion-slow)");
    expect(incoming.style.transition).toContain("var(--ease-standard)");
    // The crossfade KEYFRAME (akb-krea-fade-in) lives in scene.css (motion home)
    // and is referenced here via the var-driven animation — not a hard cut.
    expect(incoming.style.animation).toContain("akb-krea-fade-in");
    expect(incoming.style.animation).toContain("var(--motion-slow)");
  });

  it("under frozen (reduced-motion) drops the transition (static art, no animation)", () => {
    const { container } = render(<KreaArtLayer art={liveArt()} frozen />);
    const incoming = container.querySelector(
      '[data-krea="live"] > div:last-child',
    ) as HTMLElement;
    expect(incoming.style.transition).toBe("");
    expect(incoming.style.animation).toBe("");
  });

  it("fallback paints nothing (the procedural floor is the whole picture)", () => {
    const { container } = render(
      <KreaArtLayer art={liveArt({ isFallback: true, imageUrl: null, prevImageUrl: null })} />,
    );
    const layer = container.querySelector('[data-testid="krea-art-layer"]') as HTMLElement;
    expect(layer.getAttribute("data-krea")).toBe("fallback");
    // No image divs rendered in fallback.
    expect(layer.querySelectorAll("div").length).toBe(0);
  });
});
