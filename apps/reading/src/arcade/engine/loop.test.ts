import { describe, expect, it } from "vitest";

import { createDemoCartridge } from "./demoCartridge";
import { createArcadeLoop, FIXED_DT_SEC } from "./loop";
import { createSeededRng } from "./rng";
import type { InputState } from "./types";

const emptyInput = (): InputState => ({
  pointer: null,
  pointerDown: false,
  pointerPressed: false,
  pointerReleased: false,
  keysDown: new Set(),
  keysPressed: new Set(),
});

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
});
