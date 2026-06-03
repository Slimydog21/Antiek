import { REEL_MAX_PX_PER_S, REEL_SETTLE_EPSILON_PX, REEL_TAU_MS } from "./iceFishingConstants";

export interface Vec2 {
  x: number;
  y: number;
}

export interface ReelConfig {
  tauMs: number;
  maxPxPerS: number;
}

export const DEFAULT_REEL_CONFIG: ReelConfig = {
  tauMs: REEL_TAU_MS,
  maxPxPerS: REEL_MAX_PX_PER_S,
};

/**
 * One exponential step toward lagged hook center (SPR-15). Never use live pointer.
 */
export function reelStep(
  pos: Vec2,
  target: Vec2,
  dtMs: number,
  cfg: ReelConfig = DEFAULT_REEL_CONFIG,
): Vec2 {
  if (dtMs <= 0) return pos;
  const alpha = 1 - Math.exp(-dtMs / cfg.tauMs);
  let dx = (target.x - pos.x) * alpha;
  let dy = (target.y - pos.y) * alpha;
  const maxStep = (cfg.maxPxPerS * dtMs) / 1000;
  const mag = Math.hypot(dx, dy);
  if (mag > maxStep && mag > 0) {
    const s = maxStep / mag;
    dx *= s;
    dy *= s;
  }
  return { x: pos.x + dx, y: pos.y + dy };
}

export function isReelSettled(
  pos: Vec2,
  target: Vec2,
  epsilon = REEL_SETTLE_EPSILON_PX,
): boolean {
  return Math.hypot(target.x - pos.x, target.y - pos.y) <= epsilon;
}