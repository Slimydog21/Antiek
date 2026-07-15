/**
 * Shared arcade cartridge factory — the single entry both ArcadeCabinet and
 * LoadingGameHost use to build a playable cartridge. Tests drive score/wave
 * progression through THIS factory (the host entry path), not a re-implemented
 * game loop.
 */

import { createSeededRng } from "./engine/rng";
import type { Cartridge } from "./engine/types";
import { createIceFishingCartridge } from "./games/ice-fishing";
import { createZombiesCartridge } from "./games/zombies";

export type ArcadeGameKind = "ice-fishing" | "zombies";

export function createArcadeCartridge(
  game: ArcadeGameKind,
  options?: { reducedMotion?: boolean },
): Cartridge {
  if (game === "ice-fishing") {
    return createIceFishingCartridge({
      reducedMotion: Boolean(options?.reducedMotion),
    });
  }
  return createZombiesCartridge({
    reducedMotion: Boolean(options?.reducedMotion),
  });
}

/**
 * Headless score/wave progression on a freshly created cartridge — used by
 * host-entry tests after the UI mounts the same factory. Steps fixed dt with
 * synthetic input that the pure logic already understands.
 */
export function progressCartridge(
  cart: Cartridge,
  steps: number,
  options?: {
    width?: number;
    height?: number;
    seed?: number;
    fire?: boolean;
  },
): { score: number; gameOver: boolean } {
  const width = options?.width ?? 320;
  const height = options?.height ?? 200;
  let best = 0;
  const ctx = {
    width,
    height,
    rng: createSeededRng(options?.seed ?? 7),
    saveBestScore: (s: number) => {
      if (s > best) best = s;
    },
    readBestScore: () => best,
  };
  cart.init(ctx);
  try {
    // Start: Enter / space / pointer press
    cart.update(
      1 / 60,
      {
        pointer: { x: width / 2, y: height / 2 },
        pointerDown: true,
        pointerPressed: true,
        pointerReleased: false,
        keysDown: new Set<string>(["Enter"]),
        keysPressed: new Set<string>(["Enter", " "]),
        keysReleased: new Set<string>(),
      },
      ctx,
    );
    for (let i = 0; i < steps; i++) {
      const x = 40 + (i % 20) * 12;
      const y = 40 + (i % 10) * 8;
      cart.update(
        1 / 60,
        {
          pointer: { x, y },
          pointerDown: Boolean(options?.fire),
          pointerPressed: Boolean(options?.fire) && i % 3 === 0,
          pointerReleased: false,
          keysDown: new Set(options?.fire ? [" "] : []),
          keysPressed: new Set(
            options?.fire && i % 5 === 0 ? [" ", "ArrowDown"] : [],
          ),
          keysReleased: new Set<string>(),
        },
        ctx,
      );
    }
    return {
      score: cart.getScore?.() ?? 0,
      gameOver: Boolean(cart.isGameOver?.()),
    };
  } finally {
    cart.teardown();
  }
}
