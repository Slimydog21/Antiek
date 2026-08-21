import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  createZombiesState,
  stepZombies,
  type ZombiesState,
} from "./logic";

/** BO1 arcade zombies–inspired wait easter egg (paperclip undead, wholesome). */
export function createZombiesCartridge(options?: {
  reducedMotion?: boolean;
}): Cartridge {
  let state: ZombiesState | null = null;
  const reduced = Boolean(options?.reducedMotion);

  return {
    id: "paperclip-zombies",
    meta: {
      title: "Paperclip Zombies",
      blurb: "Defend the fort while deep research runs.",
      style: "zombies-arcade",
    },
    init(ctx: GameContext) {
      state = createZombiesState({
        width: ctx.width,
        height: ctx.height,
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
      if (state.phase === "gameover") {
        ctx.saveBestScore(state.score);
      }
    },
    render(c2d, ctx) {
      if (!state) return;
      const s = state;
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      c2d.fillStyle = "#1b202a";
      c2d.fillRect(0, 0, ctx.width, ctx.height);
      // Fort
      c2d.fillStyle = "#f5df24";
      c2d.fillRect(0, 0, s.fortX, ctx.height);
      c2d.fillStyle = "#151515";
      c2d.font = "10px system-ui, sans-serif";
      c2d.fillText("W", 8, ctx.height / 2);
      // Zombies (paperclips)
      for (const z of s.zombies) {
        c2d.fillStyle = "#cfcfcf";
        c2d.fillRect(z.x, z.y, z.w, z.h);
        c2d.strokeStyle = "#6b6b6b";
        c2d.strokeRect(z.x + 2, z.y + 2, z.w - 4, z.h - 4);
      }
      c2d.fillStyle = "#eef1f6";
      c2d.font = "12px system-ui, sans-serif";
      c2d.fillText(`Wave ${s.wave}  Score ${s.score}  Lives ${s.lives}`, 8, 16);
      if (s.phase === "ready") {
        c2d.fillText("Click to start — Esc exits", 8, ctx.height - 12);
      } else if (s.phase === "gameover") {
        c2d.fillText("Fort fallen — Enter to retry", 8, ctx.height - 12);
      } else if (s.phase === "exited") {
        c2d.fillText("Exited — research awaits", 8, ctx.height - 12);
      }
    },
    teardown() {
      state = null;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () =>
      state?.phase === "gameover" || state?.phase === "exited",
  };
}
