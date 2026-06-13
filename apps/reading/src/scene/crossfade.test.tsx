/**
 * crossfade.test.tsx — AMS-v2 SPR-05 M2 crossfade mechanics, REBUILT for ALC
 * SPR-06 M3 (choreographed, INTERRUPTIBLE crossfade).
 *
 * On a NO-GO (no generative stream), the Krea art is a SLOW, mood-gated tint
 * that swaps a handful of times a session. When it swaps it must CROSSFADE (no
 * hard cut), the procedural floor must keep ticking THROUGH the swap (the
 * crossfade never gates the clock), and — NEW in SPR-06 — the crossfade must be
 * INTERRUPTIBLE: a mood flip mid-fade retargets from the current visual state
 * rather than restarting.
 *
 * The DOM-level mechanics changed in M3: the SPR-04 key-remount @keyframes
 * became a two PERSISTENT slot CSS opacity TRANSITION (KreaArtLayer +
 * crossfadeMachine). These tests pin the NEW mechanics; the interruption STATE
 * MACHINE has its own pure unit test in crossfadeMachine.test.ts (rigor #3).
 *
 * The *visual* "the procedural layers kept moving while the art crossfaded" is
 * the e2e pixel-diff gate; here we pin the swap mechanics + token usage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, renderHook } from "@testing-library/react";
import { waitFor } from "@testing-library/react";

import { useSceneArt } from "./useSceneArt";
import { subscribeSceneClock } from "./useSceneClock";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import { CROSSFADE } from "../design/motion/sceneMotion";
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

describe("M2/M3 — a new generated frame triggers a crossfade (no hard cut); clock keeps ticking", () => {
  it("promotes current→prev and bumps fadeKey on the second frame; the clock keeps ticking across the swap", async () => {
    const { pump } = installControllableRaf();
    const { fn } = liveFetcher();

    const { result, rerender } = renderHook(
      ({ mood }: { mood: SceneMood }) => useSceneArt(mood, fn),
      { initialProps: { mood: DAY } },
    );

    await waitFor(() => expect(result.current.imageUrl).toBe("https://art/day.png"));
    const fadeKey1 = result.current.fadeKey;
    expect(fadeKey1).toBeGreaterThan(0);
    expect(result.current.prevImageUrl).toBeNull();

    const framesBefore: number[] = [];
    let stop = subscribeSceneClock((_t, f) => framesBefore.push(f), {
      reducedMotion: false,
    });
    pump(30);
    stop();
    expect(framesBefore.at(-1)).toBe(30);

    rerender({ mood: NIGHT });
    await waitFor(() => expect(result.current.imageUrl).toBe("https://art/night.png"));

    // CROSSFADE MECHANICS (useSceneArt side, unchanged): previous URL retained,
    // fadeKey bumped — KreaArtLayer turns this into a two-slot transition.
    expect(result.current.prevImageUrl).toBe("https://art/day.png");
    expect(result.current.fadeKey).toBeGreaterThan(fadeKey1);

    const framesAfter: number[] = [];
    stop = subscribeSceneClock((_t, f) => framesAfter.push(f), { reducedMotion: false });
    pump(30);
    stop();
    expect(framesAfter).toHaveLength(30);
    expect(framesAfter[0]).toBe(1);
    expect(framesAfter[29]).toBe(30);
  });
});

describe("M3 — KreaArtLayer is a two-slot opacity TRANSITION (interruptible), tokenized, fallback paints nothing", () => {
  const liveArt = (over: Partial<SceneArt> = {}): SceneArt => ({
    imageUrl: "https://art/night.png",
    prevImageUrl: "https://art/day.png",
    fadeKey: 2,
    isFallback: false,
    status: "ready",
    reason: null,
    ...over,
  });

  it("paints the live art into a persistent slot with the tokenized opacity transition (CROSSFADE.ms/easeIn) — no @keyframes", () => {
    const { container } = render(<KreaArtLayer art={liveArt()} />);
    const layer = container.querySelector('[data-testid="krea-art-layer"]') as HTMLElement;
    expect(layer.getAttribute("data-krea")).toBe("live");

    // At least one slot paints the live art; it carries the tokenized transition.
    const slots = Array.from(
      container.querySelectorAll<HTMLElement>("[data-krea-slot]"),
    );
    expect(slots.length).toBeGreaterThanOrEqual(1);
    const front = slots.find((s) => s.style.opacity === String(CROSSFADE.paintedOpacity));
    expect(front).toBeTruthy();
    expect(front!.style.transition).toContain("opacity");
    expect(front!.style.transition).toContain(CROSSFADE.ms);
    expect(front!.style.transition).toContain(CROSSFADE.easeIn);
    // The crossfade is a TRANSITION, not a keyframe animation (interruptible).
    expect(front!.style.animation).toBe("");
    // GPU-cheap hint.
    expect(front!.style.willChange).toBe("opacity");
  });

  it("under frozen (reduced-motion) the transition collapses to the near-instant dissolve (opacity only, no transform/keyframe)", () => {
    const { container } = render(<KreaArtLayer art={liveArt()} frozen />);
    const slot = container.querySelector<HTMLElement>("[data-krea-slot]")!;
    // Still an opacity transition (a designed dissolve), but near-instant.
    expect(slot.style.transition).toContain("opacity");
    expect(slot.style.transition).toContain(CROSSFADE.reducedMs);
    // Never a transform transition, never a keyframe.
    expect(slot.style.transition).not.toContain("transform");
    expect(slot.style.animation).toBe("");
  });

  it("fallback paints nothing (no slots, no image divs) — the procedural floor is the whole picture", () => {
    const { container } = render(
      <KreaArtLayer art={liveArt({ isFallback: true, imageUrl: null, prevImageUrl: null })} />,
    );
    const layer = container.querySelector('[data-testid="krea-art-layer"]') as HTMLElement;
    expect(layer.getAttribute("data-krea")).toBe("fallback");
    // No slot has ever been painted → no image divs (the badge self-gates to
    // null with no AuthProvider). The layer is truly empty.
    expect(layer.querySelectorAll("[data-krea-slot]").length).toBe(0);
    expect(layer.querySelectorAll("div").length).toBe(0);
  });
});
