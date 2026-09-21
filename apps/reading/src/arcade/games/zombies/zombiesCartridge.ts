import type { Cartridge, GameContext, InputState } from "../../engine/types";
import type { Mode } from "../../../design/tokens";
import { ARCADE_CARTRIDGE_META } from "../../cartridgeMeta";
import { createZombiesState, stepZombies, type ZombiesState } from "./logic";
import { drawZombiesScene } from "./zombiesVisuals";

/** BO1 arcade zombies–inspired wait easter egg (paperclip undead, wholesome). */
export function createZombiesCartridge(options?: {
  reducedMotion?: boolean;
  lives?: number;
  /** App light/dark mode; the scene follows it (D10 — no fixed pinning). */
  mode?: Mode;
}): Cartridge {
  let state: ZombiesState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  const mode = options?.mode ?? "day";
  let terminalReported = false;

  return {
    id: "paperclip-zombies",
    meta: ARCADE_CARTRIDGE_META.zombies,
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
      // Escape has ONE owner: the host shell. ResearchWaitArcade intercepts
      // Escape in the capture phase (focus restore included), so this exit
      // path never fires there — it remains for hosts that mount the
      // cartridge without their own exit chrome.
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
      drawZombiesScene(c2d, state, ctx.width, ctx.height, mode);
    },
    teardown() {
      state = null;
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "gameover" || state?.phase === "exited",
  };
}
