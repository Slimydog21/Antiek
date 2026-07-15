import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  createIceFishingState,
  stepIceFishing,
  type IceFishingState,
} from "./logic";
import {
  createIceFishingVisualKit,
  renderIceFishing,
  type IceFishingVisualKit,
} from "./visuals";

/** Club Penguin–inspired ice fishing cartridge. */
export function createIceFishingCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
  visualKit?: IceFishingVisualKit;
}): Cartridge {
  let state: IceFishingState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const visualKit = options?.visualKit ?? createIceFishingVisualKit();

  return {
    id: "ice-fishing",
    meta: {
      title: "Ice Fishing",
      blurb: "Drop the line, catch fish, avoid the boot.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
      terminalReported = false;
      visualKit.load();
      state = createIceFishingState({
        width: ctx.width,
        height: ctx.height,
        lives: options?.lives,
        reducedMotion: reduced,
      });
    },
    update(dt, input: InputState, ctx: GameContext) {
      if (!state) return;
      const aimX = input.pointer?.x ?? null;
      const drop =
        input.pointerPressed ||
        input.keysPressed.has(" ") ||
        input.keysPressed.has("ArrowDown");
      const reel =
        input.keysPressed.has("ArrowUp") || input.keysPressed.has("w");
      const start =
        input.keysPressed.has("Enter") || input.keysPressed.has(" ");
      state = stepIceFishing(state, dt, { aimX, drop, reel, start }, ctx.rng);
      if (state.phase === "gameover" && !terminalReported) {
        ctx.saveBestScore(state.score);
        terminalReported = true;
      } else if (state.phase !== "gameover") {
        terminalReported = false;
      }
    },
    render(c2d, ctx) {
      if (!state) return;
      renderIceFishing(c2d, ctx, state, visualKit);
    },
    teardown() {
      visualKit.dispose();
      state = null;
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover",
  };
}
