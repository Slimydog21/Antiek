import type { Cartridge, GameContext, InputState } from "../../engine/types";
import { aliasFor, sun, surface } from "../../../design/tokens";
import { createZombiesState, stepZombies, type ZombiesState } from "./logic";

/** BO1 arcade zombies–inspired wait easter egg (paperclip undead, wholesome). */
export function createZombiesCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
}): Cartridge {
  let state: ZombiesState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const night = aliasFor("night");

  return {
    id: "paperclip-zombies",
    meta: {
      title: "Paperclip Zombies",
      blurb: "Defend the fort while deep research runs.",
      style: "zombies-arcade",
    },
    init(ctx: GameContext) {
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
      const s = state;
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      c2d.fillStyle = surface.night[4];
      c2d.fillRect(0, 0, ctx.width, ctx.height);
      // Fort
      c2d.fillStyle = sun.base;
      c2d.fillRect(0, 0, s.fortX, ctx.height);
      c2d.fillStyle = surface.day[9];
      c2d.font = "10px system-ui, sans-serif";
      c2d.fillText("W", 8, ctx.height / 2);
      // Zombies (paperclips)
      for (const z of s.zombies) {
        c2d.fillStyle = surface.night[8];
        c2d.fillRect(z.x, z.y, z.w, z.h);
        c2d.strokeStyle = surface.night[7];
        c2d.strokeRect(z.x + 2, z.y + 2, z.w - 4, z.h - 4);
      }
      c2d.fillStyle = night.text;
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
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover" || state?.phase === "exited",
  };
}
