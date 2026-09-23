/**
 * scene-heartbeat.test.tsx — the scene runs on ONE requestAnimationFrame
 * heartbeat, never re-renders React per frame, and keeps pointer parallax
 * inside its ±MAX_PARALLAX_PX ceiling in real CSS pixels.
 *
 * Why this file exists (design audit 2026-09-23, M1 + B1): the scene claimed
 * "one heartbeat" while running three loops (the useSceneClock hook plus one
 * per canvas painter), re-rendered the whole Scene tree every frame through
 * `setClock`, and added the pointer shift to the peaks in 0-100 viewBox units,
 * so the "±8px" ceiling rendered as ±8% of the viewport height. The older
 * tests checked constants and the imperative seam in isolation; these mount
 * the real compositor and count what the browser would be asked to do.
 *
 * jsdom has no 2D canvas, so Clouds and Snow would bail before subscribing and
 * hide their loops. A recording fake context makes them subscribe exactly as
 * they do in a browser.
 */
import { Profiler } from "react";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Scene } from "./Scene";
import { MAX_PARALLAX_PX } from "./peaks";
import { DRIFT } from "../design/motion/sceneMotion";
import type { SceneResult, SceneState } from "../api/krea";

vi.mock("../krea/useKreaStatus", () => ({
  useKreaStatus: () => ({ status: "loading", data: null, error: null }),
}));

const fallbackFetch = async (s: SceneState): Promise<SceneResult> => ({
  enabled: false,
  isFallback: true,
  reason: "no_key",
  scene_key: s.mood,
});

/** A rAF that keeps EVERY pending callback (not just the last), so the number
 *  of live loops is observable: after a frame, each loop has re-armed once. */
function installRafQueue() {
  let pending = new Map<number, FrameRequestCallback>();
  let nextId = 0;
  let ts = 0;
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn((cb: FrameRequestCallback) => {
      nextId += 1;
      pending.set(nextId, cb);
      return nextId;
    }),
  );
  vi.stubGlobal(
    "cancelAnimationFrame",
    vi.fn((id: number) => {
      pending.delete(id);
    }),
  );
  return {
    /** Callbacks waiting for the next frame = loops currently alive. */
    live: () => pending.size,
    /** Run one display frame (+16ms) inside act so React flushes. */
    frame: () => {
      ts += 16;
      const batch = [...pending.values()];
      pending = new Map();
      act(() => {
        for (const cb of batch) cb(ts);
      });
    },
  };
}

/** A 2D context that records paints, so Clouds + Snow subscribe for real. */
function installFakeCanvas() {
  const paints = { clear: 0 };
  const noop = () => {};
  const ctx = {
    clearRect: () => {
      paints.clear += 1;
    },
    createRadialGradient: () => ({ addColorStop: noop }),
    beginPath: noop,
    ellipse: noop,
    arc: noop,
    fill: noop,
    globalAlpha: 1,
    globalCompositeOperation: "source-over",
    fillStyle: "",
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => ctx as unknown as CanvasRenderingContext2D,
  );
  return paints;
}

function stubMatchMedia(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
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

/** The vertical translation of a peak band wrapper, in px (0 when unset). */
function bandShiftPx(el: Element | undefined): number {
  const t = (el as HTMLElement | undefined)?.style.transform ?? "";
  const m = t.match(/translate(?:3d)?\(\s*[-\d.]+px,\s*([-\d.e]+)px/);
  return m ? Number(m[1]) : 0;
}

beforeEach(() => stubMatchMedia(false));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("scene heartbeat — one loop for every animated layer", () => {
  it("runs exactly ONE rAF loop while clouds and snow both repaint every frame", () => {
    const raf = installRafQueue();
    const paints = installFakeCanvas();
    render(<Scene fetchScene={fallbackFetch} reducedMotion={false} />);

    for (let i = 0; i < 30; i++) {
      const before = paints.clear;
      raf.frame();
      // One heartbeat re-armed itself; nothing else is looping.
      expect(raf.live()).toBe(1);
      // ...and that one heartbeat drove BOTH canvas painters this frame.
      expect(paints.clear - before).toBe(2);
    }
  });

  it("does not re-render React per frame (the heartbeat writes the DOM, not state)", () => {
    const raf = installRafQueue();
    installFakeCanvas();
    let commits = 0;
    render(
      <Profiler id="scene" onRender={() => (commits += 1)}>
        <Scene fetchScene={fallbackFetch} reducedMotion={false} />
      </Profiler>,
    );
    raf.frame(); // let mount-time effects settle
    const settled = commits;
    for (let i = 0; i < 30; i++) raf.frame();
    expect(commits - settled).toBe(0);
  });

  it("pointer parallax rides the same heartbeat and stays within ±MAX_PARALLAX_PX in px", () => {
    const raf = installRafQueue();
    installFakeCanvas();
    const { container } = render(<Scene fetchScene={fallbackFetch} reducedMotion={false} />);
    const paths = () =>
      Array.from(container.querySelectorAll('[data-testid="procedural-sky"] path')).map(
        (p) => p.getAttribute("d"),
      );
    const geometryAtRest = paths();
    expect(geometryAtRest).toHaveLength(3);

    // Pointer to the very bottom of the viewport: ny = +1, the worst case.
    act(() => {
      window.dispatchEvent(
        new MouseEvent("pointermove", { clientX: 10, clientY: window.innerHeight }),
      );
    });
    for (let i = 0; i < 180; i++) {
      raf.frame();
      expect(raf.live()).toBe(1); // no second loop for the parallax easing
    }

    const bands = Array.from(container.querySelectorAll("[data-peak-band]"));
    expect(bands).toHaveLength(3);
    const near = bandShiftPx(bands[2]);
    const far = bandShiftPx(bands[0]);
    // Near band (depth 1) settles at the pointer ceiling, plus at most the
    // ambient drift amplitude; far band (depth .25) moves a quarter of that.
    expect(near).toBeGreaterThan(MAX_PARALLAX_PX - 1);
    expect(Math.abs(near)).toBeLessThanOrEqual(MAX_PARALLAX_PX + DRIFT.peaks.yAmplitudePx);
    expect(Math.abs(far)).toBeLessThan(Math.abs(near) / 2);
    // The shift is a transform in px; the ridge geometry is never rewritten.
    expect(paths()).toEqual(geometryAtRest);
  });

  it("frozen (reduced motion): no loop at all and bands sit at zero shift", () => {
    const raf = installRafQueue();
    installFakeCanvas();
    const { container } = render(<Scene fetchScene={fallbackFetch} reducedMotion />);
    expect(raf.live()).toBe(0);
    act(() => {
      window.dispatchEvent(new MouseEvent("pointermove", { clientX: 10, clientY: 700 }));
    });
    expect(raf.live()).toBe(0);
    const bands = Array.from(container.querySelectorAll("[data-peak-band]"));
    expect(bands).toHaveLength(3);
    for (const band of bands) expect(bandShiftPx(band)).toBe(0);
  });
});
