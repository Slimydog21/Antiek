import { describe, expect, it, vi } from "vitest";

import type { GameContext, InputState } from "../../engine/types";
import { createZombiesCartridge } from "./zombiesCartridge";

const input = (keys: string[] = []): InputState => ({
  pointer: null,
  pointerDown: false,
  pointerPressed: false,
  pointerReleased: false,
  keysDown: new Set(keys),
  keysPressed: new Set(keys),
});

const pointerPress = (): InputState => ({
  ...input(),
  pointer: { x: 50, y: 50 },
  pointerDown: true,
  pointerPressed: true,
});

describe("Paperclip Zombies cartridge lifecycle", () => {
  it("saves best score once when the fort first falls", () => {
    const saveBestScore = vi.fn();
    const ctx: GameContext = {
      width: 64,
      height: 64,
      rng: () => 0.5,
      saveBestScore,
      readBestScore: () => 0,
    };
    const cart = createZombiesCartridge({ lives: 1 });
    cart.init(ctx);
    cart.update(1 / 60, input(["Enter"]), ctx);
    for (let step = 0; step < 20 && !cart.isGameOver?.(); step++) {
      cart.update(1, input(), ctx);
    }
    expect(cart.isGameOver?.()).toBe(true);
    expect(saveBestScore).toHaveBeenCalledTimes(1);

    cart.update(1, input(), ctx);
    cart.update(1, input(), ctx);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
  });

  it("saves the current score once on voluntary exit", () => {
    const saveBestScore = vi.fn();
    const ctx: GameContext = {
      width: 100,
      height: 80,
      rng: () => 0.5,
      saveBestScore,
      readBestScore: () => 0,
    };
    const cart = createZombiesCartridge({ reducedMotion: true });
    cart.init(ctx);
    cart.update(1 / 60, pointerPress(), ctx);
    cart.update(1 / 60, pointerPress(), ctx);
    expect(cart.getScore?.()).toBe(1);

    cart.update(1 / 60, input(["Escape"]), ctx);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
    expect(saveBestScore).toHaveBeenCalledWith(1);
    cart.update(1 / 60, input(), ctx);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
  });
});
