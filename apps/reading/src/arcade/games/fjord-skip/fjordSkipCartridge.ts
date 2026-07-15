import type { Cartridge, GameContext, InputState } from "../../engine/types";
import { accent, aliasFor, sun, surface } from "../../../design/tokens";
import {
  createFjordSkipState,
  LANE_COUNT,
  laneToX,
  RING_X_RATIOS,
  stepFjordSkip,
  waterLineY,
  TOTAL_THROWS,
  type FjordSkipState,
} from "./logic";
import type { FjordSkipBackdropRef } from "./fjordSkipBackdrop";

/** Ring radii must match logic.ts — rendered here, collision-owned there. */
const RING_RADII = [10, 16, 24] as const;
const RING_COLOURS_INNER = [
  accent.aurora.day,
  accent.emperor.day,
  sun.base,
] as const;

/** Fjord Skip cartridge — aim, charge, skip a pebble across the fjord. */
export function createFjordSkipCartridge(options?: {
  reducedMotion?: boolean;
  backdrop?: FjordSkipBackdropRef;
}): Cartridge {
  let state: FjordSkipState | null = null;
  const reduced = Boolean(options?.reducedMotion);
  let terminalReported = false;
  const day = aliasFor("day");

  return {
    id: "fjord-skip",
    meta: {
      title: "Fjord Skip",
      blurb: "Take a thinking break — skip a pebble across the fjord.",
      style: "club-penguin",
    },
    init(ctx: GameContext) {
      terminalReported = false;
      state = createFjordSkipState({
        width: ctx.width,
        height: ctx.height,
        reducedMotion: reduced,
      });
    },
    update(dt, input: InputState, ctx: GameContext) {
      if (!state) return;
      const prevPhase = state.phase;
      const laneDelta = input.keysPressed.has("ArrowLeft")
        ? -1
        : input.keysPressed.has("ArrowRight")
          ? 1
          : 0;
      const chargeHeld = input.pointerDown || input.keysDown.has(" ");
      const chargeReleased =
        input.pointerReleased || input.keysReleased.has(" ");
      const targetLane =
        input.pointerPressed && input.pointer
          ? (Math.max(
              -2,
              Math.min(2, Math.round((input.pointer.x / ctx.width) * 5 - 2.5)),
            ) as -2 | -1 | 0 | 1 | 2)
          : null;
      // Enter starts/retries but does NOT throw.
      const start = input.keysPressed.has("Enter");
      // Escape is captured by FjordSkipHost and never completes a round.
      state = stepFjordSkip(
        state,
        dt,
        {
          laneDelta,
          targetLane,
          chargeHeld,
          chargeReleased,
          start,
          exit: false,
        },
        ctx.rng,
      );
      const terminal = state.phase === "roundover";
      if (terminal && prevPhase !== "roundover" && !terminalReported) {
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

      // ── backdrop ──
      const backdrop = options?.backdrop?.current;
      if (backdrop) {
        c2d.drawImage(backdrop, 0, 0, 960, 600, 0, 0, ctx.width, ctx.height);
      } else {
        // Complete procedural fallback: fjord field.
        // Sky.
        c2d.fillStyle = surface.day[1];
        c2d.fillRect(0, 0, ctx.width, ctx.height);
        // Mountains (simple triangles).
        c2d.fillStyle = surface.day[5];
        c2d.beginPath();
        c2d.moveTo(0, ctx.height * 0.38);
        c2d.lineTo(ctx.width * 0.25, ctx.height * 0.12);
        c2d.lineTo(ctx.width * 0.5, ctx.height * 0.38);
        c2d.fill();
        c2d.fillStyle = surface.day[6];
        c2d.beginPath();
        c2d.moveTo(ctx.width * 0.35, ctx.height * 0.38);
        c2d.lineTo(ctx.width * 0.6, ctx.height * 0.08);
        c2d.lineTo(ctx.width * 0.85, ctx.height * 0.38);
        c2d.fill();
        // Water.
        c2d.fillStyle = surface.day[5];
        c2d.fillRect(
          0,
          waterLineY(ctx.height),
          ctx.width,
          ctx.height - waterLineY(ctx.height),
        );
        // Shore.
        c2d.fillStyle = surface.day[4];
        c2d.fillRect(0, waterLineY(ctx.height) - 6, ctx.width, 6);
      }

      // ── rings (code-owned, not in pixels) ──
      for (let r = RING_RADII.length - 1; r >= 0; r--) {
        const cx = ctx.width * RING_X_RATIOS[r];
        const cy = waterLineY(ctx.height) + 4;
        c2d.strokeStyle = RING_COLOURS_INNER[r];
        c2d.lineWidth = 2;
        c2d.beginPath();
        c2d.arc(cx, cy, RING_RADII[r], 0, Math.PI * 2);
        c2d.stroke();
      }

      // ── completed throw paths ──
      for (const result of s.results) {
        if (result.path.length < 2) continue;
        c2d.strokeStyle = day.textMuted;
        c2d.lineWidth = 1;
        c2d.setLineDash([3, 3]);
        c2d.beginPath();
        c2d.moveTo(result.path[0].x, result.path[0].y);
        for (let i = 1; i < result.path.length; i++) {
          c2d.lineTo(result.path[i].x, result.path[i].y);
        }
        c2d.stroke();
        c2d.setLineDash([]);
      }

      // ── active throw ──
      if (s.activeResult?.path.length) {
        const path = s.activeResult.path;
        const visible = Math.max(
          1,
          Math.ceil(path.length * Math.min(1, s.throwElapsed / 0.65)),
        );
        c2d.strokeStyle = sun.base;
        c2d.lineWidth = 3;
        c2d.beginPath();
        c2d.moveTo(path[0].x, path[0].y);
        for (let i = 1; i < visible; i++) c2d.lineTo(path[i].x, path[i].y);
        c2d.stroke();
        const pebble = path[visible - 1];
        c2d.fillStyle = day.text;
        c2d.beginPath();
        c2d.arc(pebble.x, pebble.y, 4, 0, Math.PI * 2);
        c2d.fill();
      }

      // ── aim indicator ──
      if (s.phase === "aiming" || s.phase === "charging") {
        const aimX = laneToX(s.lane, ctx.width);
        const waterY = waterLineY(ctx.height);
        c2d.fillStyle = sun.base;
        c2d.beginPath();
        c2d.arc(aimX, waterY - 14, 5, 0, Math.PI * 2);
        c2d.fill();
      }

      // ── charge meter ──
      if (s.phase === "charging") {
        const meterW = 60;
        const meterH = 6;
        const mx = laneToX(s.lane, ctx.width) - meterW / 2;
        const my = waterLineY(ctx.height) - 28;
        c2d.fillStyle = surface.day[4];
        c2d.fillRect(mx, my, meterW, meterH);
        c2d.fillStyle = sun.base;
        c2d.fillRect(mx, my, meterW * s.charge, meterH);
      }

      // ── HUD ──
      c2d.globalAlpha = 0.78;
      c2d.fillStyle = surface.day[0];
      c2d.fillRect(4, 4, 100, 42);
      if (s.phase === "ready" || s.phase === "roundover") {
        c2d.fillRect(4, ctx.height - 28, 200, 20);
      }
      c2d.globalAlpha = 1;
      c2d.fillStyle = day.text;
      c2d.font = "12px system-ui, sans-serif";
      c2d.fillText(`Score ${s.score}`, 8, 16);
      c2d.fillText(
        `Throw ${Math.min(s.throwIndex + 1, TOTAL_THROWS)} of ${TOTAL_THROWS}`,
        8,
        32,
      );
      if (s.phase === "ready") {
        c2d.fillText("← → aim · hold Space to charge", 8, ctx.height - 12);
      } else if (s.phase === "roundover") {
        c2d.fillText("Round over — Enter to retry", 8, ctx.height - 12);
      }
    },
    teardown() {
      state = null;
      terminalReported = false;
    },
    getScore: () => state?.score ?? 0,
    isGameOver: () => state?.phase === "roundover",
    getAccessibleStatus: () => {
      if (!state) return "Fjord Skip is loading.";
      const phase =
        state.phase === "ready"
          ? "Ready"
          : state.phase === "roundover"
            ? "Round over"
            : state.phase === "aiming"
              ? "Aiming"
              : state.phase === "charging"
                ? "Charging"
                : "Throwing";
      const lastResult = state.results.at(-1);
      const hitText = lastResult
        ? lastResult.hitRing > 0
          ? `${lastResult.skips} skips. Hit ring for ${lastResult.hitRing}.`
          : `${lastResult.skips} skips. Miss.`
        : "";
      return `${phase}. Lane ${state.lane + 3} of ${LANE_COUNT}. Score ${state.score}. Throw ${Math.min(state.throwIndex + 1, TOTAL_THROWS)} of ${TOTAL_THROWS}. ${hitText}`;
    },
  };
}
