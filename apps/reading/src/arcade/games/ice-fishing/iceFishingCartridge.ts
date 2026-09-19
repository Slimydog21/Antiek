import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  createIceFishingState,
  stepIceFishing,
  type IceFishingState,
} from "./logic";

/** Club Penguin–inspired ice fishing cartridge. */
export function createIceFishingCartridge(options?: {
  reducedMotion?: boolean;
}): Cartridge {
  let state: IceFishingState | null = null;
  let reduced = Boolean(options?.reducedMotion);

  return {
    id: "ice-fishing",
    meta: {
      title: "Ice Fishing",
      blurb: "Drop the line, catch fish, avoid the boot.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
      state = createIceFishingState({
        width: ctx.width,
        height: ctx.height,
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
      state = stepIceFishing(
        state,
        dt,
        { aimX, drop, reel, start },
        ctx.rng,
      );
      if (state.phase === "gameover") {
        ctx.saveBestScore(state.score);
      }
    },
    render(c2d, ctx) {
      if (!state) return;
      const s = state;
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      // Ice
      c2d.fillStyle = "#d7e8f2";
      c2d.fillRect(0, 0, ctx.width, 48);
      // Water
      c2d.fillStyle = "#3a6d8c";
      c2d.fillRect(0, 48, ctx.width, ctx.height - 48);
      // Hole
      c2d.fillStyle = "#1a3a4a";
      c2d.beginPath();
      c2d.ellipse(ctx.width / 2, 52, 40, 10, 0, 0, Math.PI * 2);
      c2d.fill();
      // Line + hook
      c2d.strokeStyle = "#f5df24";
      c2d.lineWidth = 2;
      c2d.beginPath();
      c2d.moveTo(s.hookX, 40);
      c2d.lineTo(s.hookX, s.hookY);
      c2d.stroke();
      c2d.fillStyle = "#f5df24";
      c2d.beginPath();
      c2d.arc(s.hookX, s.hookY, 5, 0, Math.PI * 2);
      c2d.fill();
      // Fish
      for (const f of s.fishes) {
        c2d.fillStyle =
          f.kind === "hazard"
            ? "#c63d24"
            : f.kind === "medium"
              ? "#f9bd2b"
              : "#8fd3a8";
        c2d.fillRect(f.x, f.y, f.w, f.h);
      }
      // HUD
      c2d.fillStyle = "#151515";
      c2d.font = "12px system-ui, sans-serif";
      c2d.fillText(`Score ${s.score}`, 8, 16);
      c2d.fillText(`Lives ${s.lives}`, 8, 32);
      if (s.phase === "ready") {
        c2d.fillText("Click / Space to fish", 8, ctx.height - 12);
      } else if (s.phase === "gameover") {
        c2d.fillText("Game over — Enter to retry", 8, ctx.height - 12);
      }
    },
    teardown() {
      state = null;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover",
  };
}
