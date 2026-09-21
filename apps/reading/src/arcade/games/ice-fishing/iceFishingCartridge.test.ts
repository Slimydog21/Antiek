import { describe, expect, it, vi } from "vitest";

import { surface, type } from "../../../design/tokens";
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

  it("paints the app mode's ramp and the token HUD font", () => {
    const ctx: GameContext = {
      width: 480,
      height: 300,
      rng: () => 0,
      saveBestScore: () => undefined,
      readBestScore: () => 0,
    };
    const renderSpy = () => {
      const fills: string[] = [];
      const state: Record<string, unknown> = {
        fillStyle: "",
        strokeStyle: "",
        lineWidth: 1,
        font: "",
      };
      const context = new Proxy(state, {
        get(target, prop) {
          if (prop === "fillRect") {
            return () => fills.push(target.fillStyle as string);
          }
          if (prop in target) return target[prop as string];
          return () => undefined;
        },
        set(target, prop, value) {
          target[prop as string] = value;
          return true;
        },
      }) as unknown as CanvasRenderingContext2D;
      return { context, fills, state };
    };

    const day = renderSpy();
    const dayCart = createIceFishingCartridge({ mode: "day" });
    dayCart.init(ctx);
    dayCart.render(day.context, ctx);
    expect(day.fills[0]).toBe(surface.day[4]);
    expect(day.state.font).toBe(`12px ${type.mono}`);
    dayCart.teardown();

    const night = renderSpy();
    const nightCart = createIceFishingCartridge({ mode: "night" });
    nightCart.init(ctx);
    nightCart.render(night.context, ctx);
    expect(night.fills[0]).toBe(surface.night[4]);
    nightCart.teardown();
  });
});
