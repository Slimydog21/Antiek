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
  it.each([
    ["pointer", { pointerPressed: true }],
    ["Space", { keysPressed: new Set([" "]) }],
    ["Arrow Down", { keysPressed: new Set(["ArrowDown"]) }],
  ])("maps %s to a first-action cast", (_name, override) => {
    const ctx: GameContext = {
      width: 480,
      height: 300,
      rng: () => 0.5,
      saveBestScore: vi.fn(),
      readBestScore: () => 0,
    };
    const cart = createIceFishingCartridge();
    cart.init(ctx);
    cart.update(
      1 / 60,
      {
        pointer: null,
        pointerDown: false,
        pointerPressed: false,
        pointerReleased: false,
        keysDown: new Set(),
        keysPressed: new Set(),
        ...override,
      },
      ctx,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Line casting");
  });

  it("maps Enter alone to a quiet first-action start", () => {
    const ctx: GameContext = {
      width: 480,
      height: 300,
      rng: () => 0.5,
      saveBestScore: vi.fn(),
      readBestScore: () => 0,
    };
    const cart = createIceFishingCartridge();
    cart.init(ctx);
    cart.update(
      1 / 60,
      {
        pointer: null,
        pointerDown: false,
        pointerPressed: false,
        pointerReleased: false,
        keysDown: new Set(["Enter"]),
        keysPressed: new Set(["Enter"]),
      },
      ctx,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Line ready");
  });

  it("uses the complete procedural field until an authored backdrop exists", () => {
    const backdrop = { current: null as CanvasImageSource | null };
    const ctx: GameContext = {
      width: 480,
      height: 300,
      rng: () => 0.5,
      saveBestScore: vi.fn(),
      readBestScore: () => 0,
    };
    const c2d = {
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      ellipse: vi.fn(),
      fill: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fillText: vi.fn(),
      drawImage: vi.fn(),
      set fillStyle(_value: string) {},
      set strokeStyle(_value: string) {},
      set lineWidth(_value: number) {},
      set font(_value: string) {},
      set globalAlpha(_value: number) {},
    } as unknown as CanvasRenderingContext2D;
    const cart = createIceFishingCartridge({ backdrop });
    cart.init(ctx);
    cart.render(c2d, ctx);
    expect(c2d.drawImage).not.toHaveBeenCalled();
    expect(c2d.fillRect).toHaveBeenCalledWith(0, 0, 480, 48);
    expect(c2d.fillRect).toHaveBeenCalledWith(0, 48, 480, 252);
    expect(c2d.ellipse).toHaveBeenCalledWith(
      240,
      52,
      40,
      10,
      0,
      0,
      Math.PI * 2,
    );

    backdrop.current = {} as CanvasImageSource;
    cart.render(c2d, ctx);
    expect(c2d.drawImage).toHaveBeenCalledWith(
      backdrop.current,
      0,
      50,
      960,
      550,
      0,
      0,
      480,
      300,
    );
  });

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
