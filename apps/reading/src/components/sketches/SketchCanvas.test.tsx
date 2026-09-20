import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SketchCanvas } from "./SketchCanvas";
import type { SketchBaseParams, SketchRender } from "./types";

const paint = vi.fn<SketchRender<SketchBaseParams>>();

beforeEach(() => {
  paint.mockClear();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    setTransform: vi.fn(),
    clearRect: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SketchCanvas", () => {
  it("paints one frame and does not start rAF under reduced-motion", () => {
    const raf = vi.fn(() => 1);
    const caf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);

    render(
      <SketchCanvas
        render={paint}
        params={{ seed: "x", t: 0 }}
        reducedMotion
        width={100}
        height={60}
        aria-label="Test sketch"
      />,
    );

    expect(screen.getByRole("img", { name: "Test sketch" })).toBeTruthy();
    expect(paint).toHaveBeenCalledTimes(1);
    const args = paint.mock.calls[0];
    expect(args?.[1]).toBe(100);
    expect(args?.[2]).toBe(60);
    expect(args?.[3].reducedMotion).toBe(true);
    expect(raf).not.toHaveBeenCalled();
  });

  it("starts rAF when motion is allowed and animate=true", () => {
    const callbacks: FrameRequestCallback[] = [];
    const raf = vi.fn((cb: FrameRequestCallback) => {
      callbacks.push(cb);
      return callbacks.length;
    });
    const caf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);

    const view = render(
      <SketchCanvas
        render={paint}
        params={{ seed: "y", t: 0 }}
        reducedMotion={false}
        animate
        width={80}
        height={40}
      />,
    );

    // initial paint + one rAF schedule
    expect(paint).toHaveBeenCalled();
    expect(raf).toHaveBeenCalled();
    // drive one frame
    const first = callbacks[0];
    first?.(16);
    expect(paint.mock.calls.length).toBeGreaterThanOrEqual(2);

    view.unmount();
    expect(caf).toHaveBeenCalled();
  });

  it("animate=false paints once even when motion is allowed", () => {
    const raf = vi.fn(() => 1);
    vi.stubGlobal("requestAnimationFrame", raf);
    render(
      <SketchCanvas
        render={paint}
        params={{ seed: "z" }}
        reducedMotion={false}
        animate={false}
      />,
    );
    expect(paint).toHaveBeenCalledTimes(1);
    expect(raf).not.toHaveBeenCalled();
  });
});
