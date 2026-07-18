import { describe, expect, it, vi } from "vitest";

import { createArcadeCartridge, progressCartridge } from "./cartridgeFactory";
import type { Cartridge } from "./engine/types";

describe("arcade cartridge factory helpers", () => {
  it.each([
    ["zombies", "paperclip-zombies"],
    ["ice-fishing", "ice-fishing"],
    ["clam-catcher", "clam-catcher"],
  ] as const)(
    "constructs the %s cartridge through the shared factory",
    (kind, id) => {
      const cart = createArcadeCartridge(kind);
      expect(cart.id).toBe(id);
      cart.teardown();
    },
  );

  it.each([
    ["clam-catcher", "clam-catcher"],
    ["ice-fishing", "ice-fishing"],
    ["zombies", "paperclip-zombies"],
  ] as const)(
    "progresses %s score under reducedMotion via shared factory densify",
    (kind, id) => {
      const cart = createArcadeCartridge(kind, { reducedMotion: true });
      expect(cart.id).toBe(id);
      // RM a11y densify: host factory path scores without re-implementing rules.
      const { score } = progressCartridge(cart, 12, { fire: true, seed: 3 });
      expect(score).toBeGreaterThan(0);
    },
  );

  it("tears down the cartridge after a successful simulation", () => {
    const teardown = vi.fn();
    const cart: Cartridge = {
      id: "lifecycle",
      meta: { title: "Lifecycle", blurb: "", style: "demo" },
      init: vi.fn(),
      update: vi.fn(),
      render: vi.fn(),
      teardown,
      getScore: () => 7,
      isGameOver: () => false,
    };
    expect(progressCartridge(cart, 2)).toEqual({ score: 7, gameOver: false });
    expect(teardown).toHaveBeenCalledTimes(1);
  });

  it("tears down even when simulation throws", () => {
    const teardown = vi.fn();
    const cart: Cartridge = {
      id: "throwing",
      meta: { title: "Throwing", blurb: "", style: "demo" },
      init: vi.fn(),
      update: vi.fn(() => {
        throw new Error("simulation failed");
      }),
      render: vi.fn(),
      teardown,
    };
    expect(() => progressCartridge(cart, 2)).toThrow("simulation failed");
    expect(teardown).toHaveBeenCalledTimes(1);
  });
});
