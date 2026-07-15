import { accent, aliasFor, sun, surface } from "../../../design/tokens";
import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  CLAM_CATCHER_TUNING,
  createClamCatcherState,
  stepClamCatcher,
  type ClamCatcherState,
} from "./logic";

export function createClamCatcherCartridge(): Cartridge {
  let state: ClamCatcherState | null = null;
  let terminalReported = false;
  const day = aliasFor("day");

  return {
    id: "clam-catcher",
    meta: {
      title: "Clam Catcher",
      blurb: "Catch pearl clams. Let the jellyfish drift past.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
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
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      c2d.fillStyle = surface.day[6];
      c2d.fillRect(0, 0, ctx.width, ctx.height);
      c2d.fillStyle = surface.day[4];
      c2d.fillRect(0, ctx.height - 22, ctx.width, 22);

      for (const entity of state.entities) {
        c2d.fillStyle =
          entity.kind === "jellyfish"
            ? accent.emperor.day
            : entity.kind === "pearl-clam"
              ? sun.glow.day
              : accent.aurora.day;
        c2d.beginPath();
        c2d.arc(entity.x, entity.y, entity.radius, Math.PI, 0);
        c2d.lineTo(entity.x + entity.radius, entity.y + entity.radius / 2);
        c2d.lineTo(entity.x - entity.radius, entity.y + entity.radius / 2);
        c2d.closePath();
        c2d.fill();
      }

      c2d.fillStyle = sun.base;
      c2d.fillRect(
        state.bucketX - CLAM_CATCHER_TUNING.bucketWidth / 2,
        ctx.height - 34,
        CLAM_CATCHER_TUNING.bucketWidth,
        CLAM_CATCHER_TUNING.bucketHeight,
      );
      c2d.fillStyle = day.text;
      c2d.font = "12px system-ui, sans-serif";
      c2d.fillText(`Score ${state.score}`, 8, 16);
      c2d.fillText(`Lives ${state.lives}`, 8, 32);
      if (state.phase === "ready") {
        c2d.fillText(
          "Pointer or arrows to catch — Enter to start",
          8,
          ctx.height - 46,
        );
      } else if (state.phase === "gameover") {
        c2d.fillText("Shift over — Enter to retry", 8, ctx.height - 46);
      }
    },
    teardown() {
      state = null;
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover",
  };
}
