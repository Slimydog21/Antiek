import { describe, expect, it, vi } from "vitest";

import type { GameContext } from "../../engine/types";
import { createClamCatcherState, type ClamCatcherState } from "./logic";
import {
  createClamCatcherVisualKit,
  renderClamCatcher,
  type ClamCatcherVisualKit,
} from "./visuals";

function context2d() {
  return {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    drawImage: vi.fn(),
    fillText: vi.fn(),
    strokeRect: vi.fn(),
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

describe("Clam Catcher authored visuals", () => {
  it("loads one project atlas and clears handlers on disposal", () => {
    const image = {
      decoding: "auto",
      onload: null,
      onerror: null,
      src: "",
    } as unknown as HTMLImageElement;
    const createImage = vi.fn(() => image);
    const kit = createClamCatcherVisualKit(createImage);
    expect(createImage).not.toHaveBeenCalled();
    kit.load();
    expect(image.src).toMatch(/clam-catcher-visual-kit-v1\.webp$/);
    expect(image.decoding).toBe("async");
    expect(kit.ready).toBe(false);
    image.onload?.(new Event("load"));
    expect(kit.ready).toBe(true);
    kit.dispose();
    expect(kit.ready).toBe(false);
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });

  it("loads a fresh image after teardown instead of stranding the fallback", () => {
    const first = { decoding: "auto", onload: null, onerror: null, src: "" };
    const second = { decoding: "auto", onload: null, onerror: null, src: "" };
    const createImage = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second);
    const kit = createClamCatcherVisualKit(
      createImage as unknown as () => HTMLImageElement,
    );
    kit.load();
    kit.dispose();
    kit.load();
    expect(createImage).toHaveBeenCalledTimes(2);
    expect(kit.image).toBe(second);
  });

  it("draws a sun rim around authored pearl-clam densify", () => {
    const c2d = context2d();
    const kit: ClamCatcherVisualKit = {
      image: {} as CanvasImageSource,
      ready: true,
      load: vi.fn(),
      dispose: vi.fn(),
    };
    const state: ClamCatcherState = {
      ...createClamCatcherState(ctx.width, ctx.height),
      phase: "playing",
      entities: [
        { id: 2, kind: "pearl-clam", x: 160, y: 100, radius: 10, points: 4 },
      ],
    };
    renderClamCatcher(c2d, ctx, state, kit);
    // ENTITY_SIZE pearl is 18×19; top-left = center - half size.
    expect(c2d.strokeRect).toHaveBeenCalledWith(
      160 - 18 / 2 + 0.5,
      100 - 19 / 2 + 0.5,
      17,
      18,
    );
  });

  it("draws every entity kind and the bucket from stable atlas cells", () => {
    const c2d = context2d();
    const image = {} as CanvasImageSource;
    const kit: ClamCatcherVisualKit = {
      image,
      ready: true,
      load: vi.fn(),
      dispose: vi.fn(),
    };
    const state: ClamCatcherState = {
      ...createClamCatcherState(ctx.width, ctx.height),
      phase: "playing",
      entities: [
        { id: 1, kind: "common-clam", x: 80, y: 90, radius: 9, points: 1 },
        { id: 2, kind: "pearl-clam", x: 160, y: 100, radius: 10, points: 4 },
        { id: 3, kind: "jellyfish", x: 240, y: 110, radius: 13, points: 0 },
      ],
    };
    renderClamCatcher(c2d, ctx, state, kit);
    expect(c2d.drawImage).toHaveBeenCalledTimes(4);
    expect(
      vi.mocked(c2d.drawImage).mock.calls.map((call) => call.slice(1, 5)),
    ).toEqual([
      [149, 150, 348, 296],
      [708, 97, 359, 386],
      [167, 627, 310, 514],
      [657, 677, 443, 422],
    ]);
    expect(
      vi.mocked(c2d.drawImage).mock.calls.map((call) => call.slice(5, 9)),
    ).toEqual([
      [71, 82.5, 18, 15],
      [151, 90.5, 18, 19],
      [232, 97, 16, 26],
      [211, 266, 58, 55],
    ]);
  });

  it("keeps a deterministic token-based fallback before the atlas is ready", () => {
    const c2d = context2d();
    const state: ClamCatcherState = {
      ...createClamCatcherState(ctx.width, ctx.height),
      entities: [
        { id: 1, kind: "common-clam", x: 80, y: 90, radius: 9, points: 1 },
      ],
    };
    renderClamCatcher(c2d, ctx, state, {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    });
    expect(c2d.drawImage).not.toHaveBeenCalled();
    expect(c2d.arc).toHaveBeenCalledTimes(1);
    expect(c2d.fillText).toHaveBeenCalledWith("SCORE 0", 10, 18);
  });

  it("draws Club Penguin catch-streak HUD only while streak is live", () => {
    const c2d = context2d();
    const emptyKit = {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    };
    const cold = createClamCatcherState(ctx.width, ctx.height);
    renderClamCatcher(c2d, ctx, cold, emptyKit);
    expect(
      vi.mocked(c2d.fillText).mock.calls.some((call) =>
        String(call[0]).startsWith("x"),
      ),
    ).toBe(false);

    renderClamCatcher(
      c2d,
      ctx,
      { ...cold, streak: 2, score: 5 },
      emptyKit,
    );
    expect(c2d.fillText).toHaveBeenCalledWith(
      "x3",
      Math.max(96, ctx.width * 0.42),
      18,
    );
  });

  it("brags peak catch-streak on gameover HUD", () => {
    const c2d = context2d();
    const emptyKit = {
      image: null,
      ready: false,
      load() {},
      dispose() {},
    };
    const cold = createClamCatcherState(ctx.width, ctx.height);
    renderClamCatcher(
      c2d,
      ctx,
      { ...cold, phase: "gameover", maxStreak: 3, score: 12, lives: 0 },
      emptyKit,
    );
    expect(c2d.fillText).toHaveBeenCalledWith("BEST x3", 10, ctx.height - 32);
  });
});
