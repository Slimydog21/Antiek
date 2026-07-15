import { describe, expect, it, vi } from "vitest";

import { createDemoCartridge } from "./demoCartridge";
import { createArcadeLoop, FIXED_DT_SEC } from "./loop";
import { createSeededRng } from "./rng";
import type { Cartridge, GameContext, InputState } from "./types";

const emptyInput = (): InputState => ({
  pointer: null,
  pointerDown: false,
  pointerPressed: false,
  pointerReleased: false,
  keysDown: new Set(),
  keysPressed: new Set(),
  keysReleased: new Set(),
});

function loopHarness(options?: { reducedMotion?: boolean }) {
  let frame: FrameRequestCallback | null = null;
  let hidden = false;
  let nextFrameId = 0;
  const cancelled: number[] = [];
  const inputs: InputState[] = [];
  const update = vi.fn();
  const render = vi.fn();
  const cartridge: Cartridge = {
    id: "harness",
    meta: { title: "Harness", blurb: "", style: "demo" },
    init: vi.fn(),
    update,
    render,
    teardown: vi.fn(),
  };
  const ctx: GameContext = {
    width: 100,
    height: 80,
    rng: createSeededRng(1),
    saveBestScore: vi.fn(),
    readBestScore: () => 0,
  };
  const loop = createArcadeLoop({
    cartridge,
    ctx,
    getInput: () => inputs.shift() ?? emptyInput(),
    getCtx2d: () => ({}) as CanvasRenderingContext2D,
    host: {
      now: () => 0,
      requestFrame: (callback) => {
        frame = callback;
        return ++nextFrameId;
      },
      cancelFrame: (id) => cancelled.push(id),
      isHidden: () => hidden,
    },
    reducedMotion: options?.reducedMotion,
  });
  const runFrame = (ms: number) => {
    const callback = frame;
    expect(callback).not.toBeNull();
    frame = null;
    callback?.(ms);
  };
  return {
    cancelled,
    inputs,
    loop,
    render,
    runFrame,
    setHidden: (value: boolean) => {
      hidden = value;
    },
    update,
  };
}

describe("arcade engine", () => {
  it("demo cartridge lifecycle order via stepOnce", () => {
    const cart = createDemoCartridge();
    const ctx = {
      width: 100,
      height: 80,
      rng: createSeededRng(1),
      saveBestScore: () => {},
      readBestScore: () => 0,
    };
    cart.init(ctx);
    const loop = createArcadeLoop({
      cartridge: cart,
      ctx,
      getInput: emptyInput,
      getCtx2d: () => null,
      headless: true,
    });
    loop.stepOnce(emptyInput());
    loop.stepOnce({
      ...emptyInput(),
      pointerPressed: true,
      pointer: { x: 1, y: 1 },
    });
    cart.teardown();
    expect(cart.log.filter((x) => x === "init").length).toBe(1);
    expect(cart.log.filter((x) => x === "update").length).toBe(2);
    expect(cart.log.filter((x) => x === "teardown").length).toBe(1);
    expect(cart.getScore?.()).toBe(1);
  });

  it("seeded rng is deterministic", () => {
    const a = createSeededRng(99);
    const b = createSeededRng(99);
    const seqA = [a(), a(), a()];
    const seqB = [b(), b(), b()];
    expect(seqA).toEqual(seqB);
    expect(FIXED_DT_SEC).toBeCloseTo(1 / 60);
  });

  it("retains a press across a zero-step frame and consumes it once", () => {
    const h = loopHarness();
    h.inputs.push({
      ...emptyInput(),
      pointerPressed: true,
      pointer: { x: 5, y: 7 },
    });
    h.loop.start();

    h.runFrame(8);
    expect(h.update).not.toHaveBeenCalled();
    expect(h.inputs).toHaveLength(1);

    h.runFrame(17);
    expect(h.update).toHaveBeenCalledTimes(1);
    expect(h.update.mock.calls[0]?.[1].pointerPressed).toBe(true);
    expect(h.inputs).toHaveLength(0);
  });

  it("does not replay a press across catch-up substeps", () => {
    const h = loopHarness();
    h.inputs.push({ ...emptyInput(), keysPressed: new Set([" "]) });
    h.loop.start();
    h.runFrame(50);

    expect(h.update).toHaveBeenCalledTimes(3);
    expect(
      h.update.mock.calls.map((call) => call[1].keysPressed.has(" ")),
    ).toEqual([true, false, false]);
  });

  it("does not replay a release across catch-up substeps", () => {
    const h = loopHarness();
    h.inputs.push({ ...emptyInput(), keysReleased: new Set([" "]) });
    h.loop.start();
    h.runFrame(50);

    expect(
      h.update.mock.calls.map((call) => call[1].keysReleased.has(" ")),
    ).toEqual([true, false, false]);
  });

  it("pauses hidden time and resumes without catch-up", () => {
    const h = loopHarness();
    h.loop.start();
    h.setHidden(true);
    h.runFrame(5_000);
    expect(h.update).not.toHaveBeenCalled();

    h.setHidden(false);
    h.runFrame(5_017);
    expect(h.update).toHaveBeenCalledTimes(1);
  });

  it("starts and stops idempotently with exact frame cancellation", () => {
    const h = loopHarness();
    h.loop.start();
    h.loop.start();
    expect(h.loop.isRunning()).toBe(true);
    h.loop.stop();
    h.loop.stop();
    expect(h.cancelled).toEqual([1]);
    expect(h.loop.isRunning()).toBe(false);
  });

  it("renders one reduced-motion still and accepts explicit steps only", () => {
    const h = loopHarness({ reducedMotion: true });
    h.loop.start();
    expect(h.render).toHaveBeenCalledTimes(1);
    expect(h.update).not.toHaveBeenCalled();

    h.loop.stepOnce({ ...emptyInput(), pointerPressed: true });
    expect(h.update).toHaveBeenCalledTimes(1);
    expect(h.render).toHaveBeenCalledTimes(2);
    h.loop.stop();
    expect(h.cancelled).toEqual([]);
  });
});
