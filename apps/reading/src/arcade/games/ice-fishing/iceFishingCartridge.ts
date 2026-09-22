import type { Cartridge, GameContext, InputState } from "../../engine/types";
import {
  accent,
  aliasFor,
  sun,
  surface,
  type,
  type Mode,
} from "../../../design/tokens";
import { ARCADE_CARTRIDGE_META } from "../../cartridgeMeta";
import {
  createIceFishingState,
  stepIceFishing,
  type IceFishingState,
} from "./logic";

/** Club Mascot–inspired ice fishing cartridge. */
export function createIceFishingCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
  /** App light/dark mode; the scene follows it (D10 — no fixed pinning). */
  mode?: Mode;
}): Cartridge {
  let state: IceFishingState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const mode = options?.mode ?? "day";
  const ramp = surface[mode];
  const aliases = aliasFor(mode);

  return {
    id: "ice-fishing",
    meta: ARCADE_CARTRIDGE_META["ice-fishing"],
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
      // Ice
      c2d.fillStyle = ramp[4];
      c2d.fillRect(0, 0, ctx.width, 48);
      // Water
      c2d.fillStyle = ramp[6];
      c2d.fillRect(0, 48, ctx.width, ctx.height - 48);
      // Hole
      c2d.fillStyle = ramp[9];
      c2d.beginPath();
      c2d.ellipse(ctx.width / 2, 52, 40, 10, 0, 0, Math.PI * 2);
      c2d.fill();
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
            ? accent.emperor[mode]
            : f.kind === "medium"
              ? sun.glow[mode]
              : accent.aurora[mode];
        c2d.fillRect(f.x, f.y, f.w, f.h);
      }
      // HUD
      c2d.fillStyle = aliases.text;
      c2d.font = `12px ${type.mono}`;
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
  };
}
