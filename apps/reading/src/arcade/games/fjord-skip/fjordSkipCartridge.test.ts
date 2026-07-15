import { describe, expect, it, vi } from "vitest";

import type { GameContext, InputState } from "../../engine/types";
import { createFjordSkipCartridge } from "./fjordSkipCartridge";

const input = (overrides: Partial<InputState> = {}): InputState => ({
  pointer: null,
  pointerDown: false,
  pointerPressed: false,
  pointerReleased: false,
  keysDown: new Set(),
  keysPressed: new Set(),
  keysReleased: new Set(),
  ...overrides,
});

const ctx = (w = 960, h = 600): GameContext => ({
  width: w,
  height: h,
  rng: () => 0.5,
  saveBestScore: vi.fn(),
  readBestScore: () => 0,
});

describe("Fjord Skip cartridge lifecycle", () => {
  it("starts on Enter alone without throwing", () => {
    const cart = createFjordSkipCartridge();
    const c = ctx();
    cart.init(c);
    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Aiming");
    expect(cart.getScore?.()).toBe(0);
  });

  it.each([
    [
      "ArrowLeft",
      { keysPressed: new Set(["ArrowLeft"]), keysDown: new Set(["ArrowLeft"]) },
    ],
    [
      "ArrowRight",
      {
        keysPressed: new Set(["ArrowRight"]),
        keysDown: new Set(["ArrowRight"]),
      },
    ],
  ])("maps %s to lane shift", (_name, override) => {
    const cart = createFjordSkipCartridge();
    const c = ctx();
    cart.init(c);
    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );
    cart.update(1 / 60, input(override), c);
    expect(cart.getAccessibleStatus?.()).toContain("Aiming");
  });

  it("maps pointer press/hold to charging and pointer release to throw", () => {
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    const c = ctx();
    cart.init(c);
    // Start.
    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Aiming");

    // Pointer down → charge.
    cart.update(
      1 / 60,
      input({
        pointerDown: true,
        pointerPressed: true,
        pointer: { x: 480, y: 300 },
      }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Charging");

    // Pointer up → throw (reduced motion resolves immediately).
    cart.update(1 / 60, input({ pointerReleased: true }), c);
    const status = cart.getAccessibleStatus?.() ?? "";
    expect(status).toMatch(/Score \d+/);
    expect(status).toMatch(/\d+ skips/);
  });

  it("maps Space to charge and release to throw", () => {
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    const c = ctx();
    cart.init(c);
    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );

    // Space down → charge.
    cart.update(
      1 / 60,
      input({ keysPressed: new Set([" "]), keysDown: new Set([" "]) }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Charging");

    // Space up → throw.
    cart.update(1 / 60, input({ keysReleased: new Set([" "]) }), c);
    const status = cart.getAccessibleStatus?.() ?? "";
    expect(status).toMatch(/Score \d+/);
  });

  it.each([
    ["left-most", 48, "Lane 1 of 5"],
    ["right-most", 912, "Lane 5 of 5"],
  ])("lets pointer input select the %s lane", (_label, x, status) => {
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    const c = ctx();
    cart.init(c);
    cart.update(1 / 60, input({ keysPressed: new Set(["Enter"]) }), c);
    cart.update(
      1 / 60,
      input({
        pointer: { x, y: 300 },
        pointerDown: true,
        pointerPressed: true,
      }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Charging");
    expect(cart.getAccessibleStatus?.()).toContain(status);
  });

  it("Escape does not start or throw — host owns it", () => {
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    const c = ctx();
    cart.init(c);
    cart.update(
      1 / 60,
      input({
        keysPressed: new Set(["Escape"]),
        keysDown: new Set(["Escape"]),
      }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Ready");
    expect(cart.isGameOver?.()).toBe(false);
    expect(cart.getScore?.()).toBe(0);
  });

  it("uses the complete procedural fallback until an authored backdrop exists", () => {
    const backdrop = { current: null as CanvasImageSource | null };
    const c2d = {
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      setLineDash: vi.fn(),
      drawImage: vi.fn(),
      fillText: vi.fn(),
      set fillStyle(_value: string) {},
      set strokeStyle(_value: string) {},
      set lineWidth(_value: number) {},
      set font(_value: string) {},
      set globalAlpha(_value: number) {},
    } as unknown as CanvasRenderingContext2D;
    const cart = createFjordSkipCartridge({ backdrop });
    const c = ctx();
    cart.init(c);
    cart.render(c2d, c);
    expect(c2d.drawImage).not.toHaveBeenCalled();
    // Procedural sky + mountains + water.
    expect(c2d.fillRect).toHaveBeenCalled();

    backdrop.current = {} as CanvasImageSource;
    cart.render(c2d, c);
    expect(c2d.drawImage).toHaveBeenCalledWith(
      backdrop.current,
      0,
      0,
      960,
      600,
      0,
      0,
      960,
      600,
    );
  });

  it("saves best score once when the round ends", () => {
    const saveBestScore = vi.fn();
    const c: GameContext = {
      width: 960,
      height: 600,
      rng: () => 0.5,
      saveBestScore,
      readBestScore: () => 0,
    };
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    cart.init(c);
    // Start.
    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );

    // Drive 6 throws in reduced motion — each resolves immediately.
    // The state machine: aiming → (pointerDown) → charging → (pointerReleased) → scored → (any) → aiming.
    for (let t = 0; t < 6; t++) {
      // Aim → charge.
      cart.update(
        1 / 60,
        input({
          pointerDown: true,
          pointerPressed: true,
          pointer: { x: 480, y: 300 },
        }),
        c,
      );
      // Release → throw resolves instantly in reduced motion.
      cart.update(1 / 60, input({ pointerReleased: true }), c);
    }
    expect(cart.isGameOver?.()).toBe(true);
    expect(saveBestScore).toHaveBeenCalledTimes(1);

    cart.update(1 / 60, input(), c);
    expect(saveBestScore).toHaveBeenCalledTimes(1);
  });

  it("provides an accessible status at every phase", () => {
    const cart = createFjordSkipCartridge({ reducedMotion: true });
    const c = ctx();
    cart.init(c);
    expect(cart.getAccessibleStatus?.()).toContain("Ready");

    cart.update(
      1 / 60,
      input({ keysPressed: new Set(["Enter"]), keysDown: new Set(["Enter"]) }),
      c,
    );
    expect(cart.getAccessibleStatus?.()).toContain("Aiming");
  });
});
