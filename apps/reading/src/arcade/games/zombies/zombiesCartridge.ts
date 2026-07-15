import type { Cartridge, GameContext, InputState } from "../../engine/types";
import { createZombiesState, stepZombies, type ZombiesState } from "./logic";
import {
  createZombiesVisualKit,
  drawZombiesScene,
  type ZombiesVisualKit,
} from "./zombiesVisuals";

/** BO1 arcade zombies–inspired wait easter egg (paperclip undead, wholesome). */
export function createZombiesCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
  visualKit?: ZombiesVisualKit;
}): Cartridge {
  let state: ZombiesState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const visualKit = options?.visualKit ?? createZombiesVisualKit();

  return {
    id: "paperclip-zombies",
    meta: {
      title: "Paperclip Zombies",
      blurb: "Defend the fort while deep research runs.",
      style: "zombies-arcade",
    },
    init(ctx: GameContext) {
      visualKit.load();
      terminalReported = false;
      state = createZombiesState({
        width: ctx.width,
        height: ctx.height,
        lives: options?.lives,
        reducedMotion: reduced,
      });
    },
    update(dt, input: InputState, ctx: GameContext) {
      if (!state) return;
      const fireAt =
        input.pointerPressed && input.pointer
          ? { x: input.pointer.x, y: input.pointer.y }
          : null;
      const start =
        input.keysPressed.has("Enter") || input.keysPressed.has(" ");
      const exit =
        input.keysPressed.has("Escape") || input.keysPressed.has("q");
      state = stepZombies(state, dt, { fireAt, start, exit }, ctx.rng);
      const terminal = state.phase === "gameover" || state.phase === "exited";
      if (terminal && !terminalReported) {
        ctx.saveBestScore(state.score);
        terminalReported = true;
      } else if (!terminal) {
        terminalReported = false;
      }
    },
    render(c2d, ctx) {
      if (!state) return;
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      drawZombiesScene(c2d, state, ctx.width, ctx.height, visualKit);
    },
    teardown() {
      state = null;
      terminalReported = false;
      visualKit.dispose();
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover" || state?.phase === "exited",
  };
}
