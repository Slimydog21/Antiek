import type { Cartridge, GameContext, InputState } from "./types";

/**
 * No-op lifecycle cartridge — proves the contract is implementable and
 * lets lifecycle-order tests spy init → update → render → teardown.
 */
export function createDemoCartridge(): Cartridge & {
  log: string[];
} {
  const log: string[] = [];
  let score = 0;
  return {
    id: "demo",
    meta: {
      title: "Demo",
      blurb: "Lifecycle harness cartridge",
      style: "demo",
    },
    log,
    init() {
      log.push("init");
      score = 0;
    },
    update(_dt, input: InputState) {
      log.push("update");
      if (input.pointerPressed) score += 1;
    },
    render() {
      log.push("render");
    },
    teardown() {
      log.push("teardown");
    },
    getScore: () => score,
    isGameOver: () => false,
  };
}

// Silence unused GameContext in public surface for tree-shaking clarity
export type DemoCtx = GameContext;
