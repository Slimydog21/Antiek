import { describe, expect, it, vi } from "vitest";

import type { GameContext } from "../../engine/types";
import { createIceFishingState, type IceFishingState } from "./logic";
import {
  createIceFishingVisualKit,
  renderIceFishing,
  type IceFishingVisualKit,
} from "./visuals";

function context2d() {
  return {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    ellipse: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    drawImage: vi.fn(),
    fillText: vi.fn(),
    strokeRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    font: "",
  } as unknown as CanvasRenderingContext2D;
}

const ctx: GameContext = {
  width: 480,
  height: 300,
  rng: () => 0.5,
  saveBestScore: vi.fn(),
  readBestScore: () => 0,
};

describe("Ice Fishing authored visuals", () => {
  it("loads one project atlas and ignores stale callbacks after disposal", () => {
    const image = { decoding: "auto", onload: null, onerror: null, src: "" };
    const kit = createIceFishingVisualKit(
      () => image as unknown as HTMLImageElement,
    );
    kit.load();
    expect(image.src).toMatch(/ice-fishing-visual-kit-v1\.webp$/);
    expect(image.decoding).toBe("async");
    const staleLoad = image.onload as unknown as () => void;
    kit.dispose();
    staleLoad();
    expect(kit.ready).toBe(false);
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });

  it("loads a fresh image after teardown", () => {
    const first = { decoding: "auto", onload: null, onerror: null, src: "" };
    const second = { decoding: "auto", onload: null, onerror: null, src: "" };
    const createImage = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second);
    const kit = createIceFishingVisualKit(
      createImage as unknown as () => HTMLImageElement,
    );
    kit.load();
    kit.dispose();
    kit.load();
    expect(createImage).toHaveBeenCalledTimes(2);
    expect(kit.image).toBe(second);
  });

  it("draws the hook and every fish kind from stable atlas cells inside hitboxes", () => {
    const c2d = context2d();
    const image = {} as CanvasImageSource;
    const kit: IceFishingVisualKit = {
      image,
      ready: true,
      load() {},
      dispose() {},
    };
    const state: IceFishingState = {
      ...createIceFishingState({ width: ctx.width, height: ctx.height }),
      phase: "playing",
      hookX: 120,
      hookY: 80,
      fishes: [
        {
          id: 1,
          kind: "small",
          x: 20,
          y: 90,
          vx: 40,
          w: 18,
          h: 10,
          points: 1,
        },
        {
          id: 2,
          kind: "medium",
          x: 80,
          y: 110,
          vx: 40,
          w: 28,
          h: 14,
          points: 3,
        },
        {
          id: 3,
          kind: "golden",
          x: 120,
          y: 100,
          vx: 40,
          w: 28,
          h: 14,
          points: 5,
        },
        {
          id: 4,
          kind: "hazard",
          x: 160,
          y: 130,
          vx: -40,
          w: 18,
          h: 10,
          points: -1,
        },
      ],
    };
    const before = structuredClone(state);
    renderIceFishing(c2d, ctx, state, kit);
    expect(state).toEqual(before);
    // hook + small + medium + golden(reuses medium atlas) + hazard
    expect(c2d.drawImage).toHaveBeenCalledTimes(5);
    const calls = vi.mocked(c2d.drawImage).mock.calls;
    expect(calls.map((call) => call.slice(1, 5))).toEqual([
      [824, 793, 183, 258],
      [62, 228, 486, 196],
      [632, 168, 569, 332],
      [632, 168, 569, 332], // golden → medium cell
      [94, 776, 466, 258],
    ]);
    const hitboxes = [
      { x: 115, y: 75, w: 10, h: 10 },
      { x: 20, y: 90, w: 18, h: 10 },
      { x: 80, y: 110, w: 28, h: 14 },
      { x: 120, y: 100, w: 28, h: 14 },
      { x: 160, y: 130, w: 18, h: 10 },
    ];
    calls.forEach((call, index) => {
      const [dx, dy, dw, dh] = call.slice(5, 9).map(Number);
      const box = hitboxes[index];
      expect(dx).toBeGreaterThanOrEqual(box.x);
      expect(dy).toBeGreaterThanOrEqual(box.y);
      expect(dx + dw).toBeLessThanOrEqual(box.x + box.w);
      expect(dy + dh).toBeLessThanOrEqual(box.y + box.h);
    });
  });

  it("mirrors left-swimming fish without moving their authored hitbox", () => {
    const c2d = context2d();
    const state: IceFishingState = {
      ...createIceFishingState({ width: ctx.width, height: ctx.height }),
      fishes: [
        {
          id: 1,
          kind: "small",
          x: 20,
          y: 90,
          vx: -40,
          w: 18,
          h: 10,
          points: 1,
        },
      ],
    };
    renderIceFishing(c2d, ctx, state, {
      image: {} as CanvasImageSource,
      ready: true,
      load() {},
      dispose() {},
    });
    expect(c2d.save).toHaveBeenCalledTimes(1);
    expect(c2d.translate).toHaveBeenCalledWith(29, 95);
    expect(c2d.scale).toHaveBeenCalledWith(-1, 1);
    expect(c2d.restore).toHaveBeenCalledTimes(1);
  });

  it("draws Club Penguin catch-streak HUD only while streak is live", () => {
    const c2d = context2d();
    const emptyKit: IceFishingVisualKit = {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    };
    const cold = createIceFishingState({ width: ctx.width, height: ctx.height });
    renderIceFishing(c2d, ctx, cold, emptyKit);
    expect(c2d.fillText).toHaveBeenCalledWith("Score 0", 8, 16);
    expect(
      vi.mocked(c2d.fillText).mock.calls.some((call) =>
        String(call[0]).startsWith("x"),
      ),
    ).toBe(false);

    renderIceFishing(
      c2d,
      ctx,
      { ...cold, streak: 2, score: 6 },
      emptyKit,
    );
    expect(c2d.fillText).toHaveBeenCalledWith("x3", Math.max(96, ctx.width * 0.42), 16);
  });

  it("brags peak catch-streak on gameover HUD", () => {
    const c2d = context2d();
    const emptyKit: IceFishingVisualKit = {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    };
    const cold = createIceFishingState({ width: ctx.width, height: ctx.height });
    renderIceFishing(
      c2d,
      ctx,
      { ...cold, phase: "gameover", maxStreak: 3, score: 12, lives: 0 },
      emptyKit,
    );
    expect(c2d.fillText).toHaveBeenCalledWith("BEST x3", 8, ctx.height - 28);
  });

  it("keeps the original token fallback before the atlas is ready", () => {
    const c2d = context2d();
    const state: IceFishingState = {
      ...createIceFishingState({ width: ctx.width, height: ctx.height }),
      fishes: [
        {
          id: 1,
          kind: "small",
          x: 20,
          y: 90,
          vx: 40,
          w: 18,
          h: 10,
          points: 1,
        },
      ],
    };
    renderIceFishing(c2d, ctx, state, {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    });
    expect(c2d.drawImage).not.toHaveBeenCalled();
    expect(c2d.arc).toHaveBeenCalledWith(
      state.hookX,
      state.hookY,
      5,
      0,
      Math.PI * 2,
    );
    expect(c2d.fillRect).toHaveBeenCalledWith(20, 90, 18, 10);
    expect(c2d.fillText).toHaveBeenCalledWith("Score 0", 8, 16);
  });

  it("draws a sun rim around authored golden fish densify", () => {
    const c2d = context2d();
    const image = {} as CanvasImageSource;
    const kit: IceFishingVisualKit = {
      image,
      ready: true,
      load() {},
      dispose() {},
    };
    const state: IceFishingState = {
      ...createIceFishingState({ width: ctx.width, height: ctx.height }),
      fishes: [
        {
          id: 7,
          kind: "golden",
          x: 50,
          y: 90,
          vx: 20,
          w: 28,
          h: 14,
          points: 5,
        },
      ],
    };
    renderIceFishing(c2d, ctx, state, kit);
    expect(c2d.strokeRect).toHaveBeenCalledWith(50.5, 90.5, 27, 13);
  });

  it("paints golden fish fallback with sun.base densify color", () => {
    const c2d = context2d();
    const state: IceFishingState = {
      ...createIceFishingState({ width: ctx.width, height: ctx.height }),
      fishes: [
        {
          id: 9,
          kind: "golden",
          x: 40,
          y: 100,
          vx: 10,
          w: 28,
          h: 14,
          points: 5,
        },
      ],
    };
    renderIceFishing(c2d, ctx, state, {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    });
    // fillStyle is set before fillRect; golden uses sun.base token.
    expect(c2d.fillRect).toHaveBeenCalledWith(40, 100, 28, 14);
    // sun.base is a non-empty CSS color string in the token system.
    expect(String(c2d.fillStyle).length).toBeGreaterThan(0);
  });
});
