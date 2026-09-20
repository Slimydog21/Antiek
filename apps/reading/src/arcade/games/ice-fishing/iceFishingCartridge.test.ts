import { describe, expect, it, vi } from "vitest";

import type { GameContext, InputState } from "../../engine/types";
import { createIceFishingCartridge } from "./iceFishingCartridge";

const input = (press = false): InputState => ({
  pointer: { x: 24, y: 48 },
  pointerDown: press,
  pointerPressed: press,
  pointerReleased: false,
  keysDown: new Set(press ? ["ArrowDown"] : []),
  keysPressed: new Set(press ? ["ArrowDown"] : []),
});

describe("Ice Fishing cartridge lifecycle", () => {
  it("saves best score once when the first hazard ends the round", () => {
    const saveBestScore = vi.fn();
    const values = [0, 0, 0.5, 0];
    let rngIndex = 0;
    const ctx: GameContext = {
      width: 64,
      height: 64,
      rng: () => values[rngIndex++ % values.length] ?? 0,
      saveBestScore,
      readBestScore: () => 0,
    };
    const cart = createIceFishingCartridge({ lives: 1 });
    cart.init(ctx);
    cart.update(1 / 60, input(true), ctx);
    for (let step = 0; step < 1_000 && !cart.isGameOver?.(); step++) {
      cart.update(1 / 60, input(step % 3 === 0), ctx);
    }
    expect(cart.isGameOver?.()).toBe(true);
    expect(saveBestScore).toHaveBeenCalledTimes(1);

    cart.update(1 / 60, input(), ctx);
    cart.update(1 / 60, input(), ctx);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
  });
});
