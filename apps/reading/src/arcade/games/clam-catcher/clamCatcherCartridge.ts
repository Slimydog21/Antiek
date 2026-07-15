import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  createClamCatcherState,
  stepClamCatcher,
  type ClamCatcherState,
} from "./logic";
import {
  createClamCatcherVisualKit,
  renderClamCatcher,
  type ClamCatcherVisualKit,
} from "./visuals";

export function createClamCatcherCartridge(options?: {
  visualKit?: ClamCatcherVisualKit;
}): Cartridge {
  let state: ClamCatcherState | null = null;
  let terminalReported = false;
  const visualKit = options?.visualKit ?? createClamCatcherVisualKit();

  return {
    id: "clam-catcher",
    meta: {
      title: "Clam Catcher",
      blurb: "Catch pearl clams. Let the jellyfish drift past.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
      visualKit.load();
      state = createClamCatcherState(ctx.width, ctx.height);
      terminalReported = false;
    },
    update(dtSec, input: InputState, ctx: GameContext) {
      if (!state) return;
      const left = input.keysDown.has("ArrowLeft");
      const right = input.keysDown.has("ArrowRight");
      const horizontal = left === right ? 0 : left ? -1 : 1;
      state = stepClamCatcher(
        state,
        dtSec,
        {
          // A held arrow intentionally overrides the last remembered pointer
          // coordinate; ArcadeMount keeps pointer state after mouse movement.
          targetX: horizontal === 0 ? (input.pointer?.x ?? null) : null,
          horizontal,
          start:
            input.pointerPressed ||
            input.keysPressed.has("Enter") ||
            input.keysPressed.has(" "),
        },
        ctx.rng,
      );
      if (state.phase === "gameover" && !terminalReported) {
        ctx.saveBestScore(state.score);
        terminalReported = true;
      } else if (state.phase !== "gameover") {
        terminalReported = false;
      }
    },
    render(c2d, ctx) {
      if (!state) return;
      renderClamCatcher(c2d, ctx, state, visualKit);
    },
    teardown() {
      state = null;
      terminalReported = false;
      visualKit.dispose();
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover",
  };
}
