import { describe, expect, it, vi } from "vitest";

import { createSeededRng } from "../../engine/rng";
import type { GameContext, InputState } from "../../engine/types";
import { createClamCatcherCartridge } from "./clamCatcherCartridge";
import { CLAM_CATCHER_TUNING } from "./logic";
import type { ClamCatcherVisualKit } from "./visuals";

const emptyInput: InputState = {
  pointer: null,
  pointerDown: false,
  pointerPressed: false,
  pointerReleased: false,
  keysDown: new Set(),
  keysPressed: new Set(),
};

describe("Clam Catcher cartridge", () => {
  it("exposes stable metadata, starts, renders, and tears down", () => {
    const visualKit: ClamCatcherVisualKit = {
      image: null,
      ready: false,
      load: vi.fn(),
      dispose: vi.fn(),
    };
    const cart = createClamCatcherCartridge({ visualKit });
    const saveBestScore = vi.fn();
    const ctx: GameContext = {
      width: 320,
      height: 200,
      rng: createSeededRng(9),
      saveBestScore,
      readBestScore: () => 0,
    };
    cart.init(ctx);
    cart.update(
      1 / 60,
      { ...emptyInput, keysPressed: new Set(["Enter"]) },
      ctx,
    );
    expect(cart.id).toBe("clam-catcher");
    expect(cart.meta.style).toBe("club-penguin");
    expect(cart.isGameOver?.()).toBe(false);
    expect(visualKit.load).toHaveBeenCalledTimes(1);

    const c2d = {
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      fillText: vi.fn(),
      fillStyle: "",
      font: "",
    } as unknown as CanvasRenderingContext2D;
    cart.render(c2d, ctx);
    expect(c2d.clearRect).toHaveBeenCalled();
    expect(saveBestScore).not.toHaveBeenCalled();
    cart.teardown();
    expect(cart.getScore?.()).toBe(0);
    expect(visualKit.dispose).toHaveBeenCalledTimes(1);
    cart.init(ctx);
    expect(visualKit.load).toHaveBeenCalledTimes(2);
    cart.teardown();
    expect(visualKit.dispose).toHaveBeenCalledTimes(2);
  });

  it("reports a terminal score once and starts a fresh shift", () => {
    const cart = createClamCatcherCartridge({
      visualKit: {
        image: null,
        ready: false,
        load: vi.fn(),
        dispose: vi.fn(),
      },
    });
    const saveBestScore = vi.fn();
    let rngCall = 0;
    const ctx: GameContext = {
      width: 320,
      height: 200,
      // Every spawn is a jellyfish positioned at the bucket centre.
      rng: () => (rngCall++ % 2 === 0 ? 0 : 0.5),
      saveBestScore,
      readBestScore: () => 0,
    };
    cart.init(ctx);
    cart.update(
      1 / 60,
      { ...emptyInput, keysPressed: new Set(["Enter"]) },
      ctx,
    );
    for (let frame = 0; frame < 1_200 && !cart.isGameOver?.(); frame += 1) {
      cart.update(
        1 / 60,
        { ...emptyInput, pointer: { x: ctx.width / 2, y: 0 } },
        ctx,
      );
    }
    expect(cart.isGameOver?.()).toBe(true);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
    expect(saveBestScore).toHaveBeenCalledWith(0);
    cart.update(1 / 60, emptyInput, ctx);
    expect(saveBestScore).toHaveBeenCalledTimes(1);

    cart.update(
      1 / 60,
      { ...emptyInput, keysPressed: new Set(["Enter"]) },
      ctx,
    );
    expect(cart.isGameOver?.()).toBe(false);
    expect(cart.getScore?.()).toBe(0);
  });

  it("lets held arrow input override a remembered pointer position", () => {
    const cart = createClamCatcherCartridge({
      visualKit: {
        image: null,
        ready: false,
        load: vi.fn(),
        dispose: vi.fn(),
      },
    });
    const ctx: GameContext = {
      width: 320,
      height: 200,
      rng: () => 0.9,
      saveBestScore: vi.fn(),
      readBestScore: () => 0,
    };
    cart.init(ctx);
    cart.update(
      1 / 60,
      { ...emptyInput, keysPressed: new Set(["Enter"]) },
      ctx,
    );
    cart.update(
      0.05,
      {
        ...emptyInput,
        pointer: { x: ctx.width / 2, y: 0 },
        keysDown: new Set(["ArrowRight"]),
      },
      ctx,
    );
    const fillRect = vi.fn();
    const c2d = {
      clearRect: vi.fn(),
      fillRect,
      beginPath: vi.fn(),
      arc: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      drawImage: vi.fn(),
      fillText: vi.fn(),
      fillStyle: "",
      font: "",
    } as unknown as CanvasRenderingContext2D;
    cart.render(c2d, ctx);
    const bucketCall = fillRect.mock.calls.find(
      (call) => call[2] === CLAM_CATCHER_TUNING.bucketWidth,
    );
    expect(bucketCall?.[0]).toBe(
      ctx.width / 2 +
        0.05 * CLAM_CATCHER_TUNING.bucketSpeed -
        CLAM_CATCHER_TUNING.bucketWidth / 2,
    );
    cart.teardown();
  });
});
