import type { Cartridge, GameContext, InputState } from "../../engine/types";
import { accent, aliasFor, sun, surface } from "../../../design/tokens";
import {
  createIceFishingState,
  stepIceFishing,
  type IceFishingState,
} from "./logic";
import type { IceFishingBackdropRef } from "./iceFishingBackdrop";

/** Club Penguin–inspired ice fishing cartridge. */
export function createIceFishingCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
  backdrop?: IceFishingBackdropRef;
}): Cartridge {
  let state: IceFishingState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const day = aliasFor("day");

  return {
    id: "ice-fishing",
    meta: {
      title: "Ice Fishing",
      blurb: "Drop the line, catch fish, avoid the boot.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
      terminalReported = false;
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
      const s = state;
      c2d.clearRect(0, 0, ctx.width, ctx.height);
      const backdrop = options?.backdrop?.current;
      if (backdrop) {
        // Crop the tall concept plate so its painted hole and waterline align
        // with the cartridge's long-standing 48–52 px logical geometry.
        c2d.drawImage(backdrop, 0, 50, 960, 550, 0, 0, ctx.width, ctx.height);
      } else {
        // Complete procedural fallback: play never depends on image decode.
        c2d.fillStyle = surface.day[4];
        c2d.fillRect(0, 0, ctx.width, 48);
        c2d.fillStyle = surface.day[6];
        c2d.fillRect(0, 48, ctx.width, ctx.height - 48);
        c2d.fillStyle = surface.day[9];
        c2d.beginPath();
        c2d.ellipse(ctx.width / 2, 52, 40, 10, 0, 0, Math.PI * 2);
        c2d.fill();
      }
      // Line + hook
      c2d.strokeStyle = sun.base;
      c2d.lineWidth = 2;
      c2d.beginPath();
      c2d.moveTo(s.hookX, 40);
      c2d.lineTo(s.hookX, s.hookY);
      c2d.stroke();
      c2d.fillStyle = sun.base;
      c2d.beginPath();
      c2d.arc(s.hookX, s.hookY, 5, 0, Math.PI * 2);
      c2d.fill();
      // Fish
      for (const f of s.fishes) {
        c2d.fillStyle =
          f.kind === "hazard"
            ? accent.emperor.day
            : f.kind === "medium"
              ? sun.glow.day
              : accent.aurora.day;
        c2d.fillRect(f.x, f.y, f.w, f.h);
      }
      // HUD
      c2d.globalAlpha = 0.78;
      c2d.fillStyle = surface.day[0];
      c2d.fillRect(4, 4, 68, 34);
      if (s.phase === "ready" || s.phase === "gameover") {
        c2d.fillRect(4, ctx.height - 28, 174, 20);
      }
      c2d.globalAlpha = 1;
      c2d.fillStyle = day.text;
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
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover",
    getAccessibleStatus: () => {
      if (!state) return "Ice Fishing is loading.";
      const phase =
        state.phase === "ready"
          ? "Ready"
          : state.phase === "gameover"
            ? "Game over"
            : "Fishing";
      const line = state.dropping
        ? "Line casting"
        : state.reeling
          ? "Line reeling"
          : "Line ready";
      return `${phase}. ${line}. Score ${state.score}. Lives ${state.lives}.`;
    },
  };
}
