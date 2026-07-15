/**
 * Fjord Skip — pure rules (aim-and-skip pebble game).
 *
 * Five aim lanes · charge meter · seeded-current deterministic arc ·
 * up to four skips across water · code-rendered rings score 1/3/5 ·
 * six-throw round · retry · discrete reduced-motion resolution.
 *
 * Determinism contract: same seed + same input trace → identical final state.
 */

/* ─── types ─────────────────────────────────────────────────────────────── */

export type FjordPhase =
  "ready" | "aiming" | "charging" | "throwing" | "scored" | "roundover";

export type AimLane = -2 | -1 | 0 | 1 | 2;

export interface FjordSkipConfig {
  width: number;
  height: number;
  reducedMotion?: boolean;
}

export interface SkipResult {
  lane: AimLane;
  skips: number;
  hitRing: 0 | 1 | 3 | 5;
  /** Pebble path points for rendering (empty in reduced-motion). */
  path: Array<{ x: number; y: number }>;
}

export interface FjordSkipState {
  phase: FjordPhase;
  score: number;
  throwIndex: number;
  /** Results of completed throws this round (length ≤ 6). */
  results: SkipResult[];
  lane: AimLane;
  charge: number;
  /** Seeded water current modifier (−1..+1). */
  current: number;
  currentSeed: number;
  width: number;
  height: number;
  reducedMotion: boolean;
  activeResult: SkipResult | null;
  throwElapsed: number;
}

/* ─── constants ─────────────────────────────────────────────────────────── */

export const TOTAL_THROWS = 6;
export const LANE_COUNT = 5;
export const LANE_INDICES: readonly AimLane[] = [-2, -1, 0, 1, 2];

/** Ring radii (code-owned, not baked into pixels). */
const RING_RADII = [10, 16, 24] as const;
const RING_SCORES = [5, 3, 1] as const;
export const RING_X_RATIOS = [0.2, 0.5, 0.8] as const;

/** Maximum deterministic skips per throw. */
const MAX_SKIPS = 4;

/* ─── state factory ─────────────────────────────────────────────────────── */

export function createFjordSkipState(cfg: FjordSkipConfig): FjordSkipState {
  return {
    phase: "ready",
    score: 0,
    throwIndex: 0,
    results: [],
    lane: 0,
    charge: 0,
    current: 0,
    currentSeed: 1,
    width: Math.max(64, cfg.width),
    height: Math.max(64, cfg.height),
    reducedMotion: Boolean(cfg.reducedMotion),
    activeResult: null,
    throwElapsed: 0,
  };
}

/* ─── helpers ───────────────────────────────────────────────────────────── */

/** Map a lane index to a CSS-pixel x coordinate. */
export function laneToX(lane: AimLane, width: number): number {
  const step = width / (LANE_COUNT + 1);
  return step * (lane + 3); // lanes -2..+2 → positions 1..5 of 6 slots
}

/** Water surface y (where pebbles begin skipping). */
export function waterLineY(height: number): number {
  return Math.floor(height * 0.62);
}

/** Centre of each ring at a given waterline. */
export function ringCentre(
  ringIndex: number,
  width: number,
  height: number,
): { x: number; y: number } {
  return {
    x: RING_X_RATIOS[ringIndex] * width,
    y: waterLineY(height) + 4,
  };
}

/** Deterministic skip resolution for one throw. */
function resolveSkip(
  state: FjordSkipState,
  charge: number,
  rng: () => number,
  reducedMotion: boolean,
): SkipResult {
  const lane = state.lane;
  const startX = laneToX(lane, state.width);
  const waterY = waterLineY(state.height);

  // Pebble arc: charge affects horizontal velocity, current adds drift.
  const hVel =
    (charge * 120 + state.current * 30) * (lane === 0 ? 0 : lane > 0 ? 1 : -1);
  const baseVx = lane === 0 ? state.current * 30 : hVel;

  // Number of skips depends on charge: 0–0.3 → 1, 0.3–0.6 → 2, 0.6–0.85 → 3, 0.85+ → 4
  const maxSkips =
    charge < 0.3 ? 1 : charge < 0.6 ? 2 : charge < 0.85 ? 3 : MAX_SKIPS;
  // Add seeded variance.
  const skipBonus = rng() > 0.7 ? 1 : 0;
  const skipCount = Math.min(MAX_SKIPS, maxSkips + skipBonus);

  // Build path and test ring collision per skip.
  // In reduced motion, path is empty — no animation plays.
  const path: Array<{ x: number; y: number }> = [];
  let hitRing: 0 | 1 | 3 | 5 = 0;
  let px = startX;
  let py = waterY;
  if (!reducedMotion) path.push({ x: px, y: py });

  for (let s = 0; s < skipCount; s++) {
    px += baseVx * (0.6 + rng() * 0.4);
    // Bounce: pebble arcs up then down.
    const bounceH = 18 + rng() * 14;
    py = waterY - bounceH;
    if (!reducedMotion) path.push({ x: px, y: py });
    py = waterY;
    if (!reducedMotion) path.push({ x: px, y: py });

    // Ring collision: check all rings at this skip position.
    for (let r = 0; r < RING_RADII.length; r++) {
      const centre = ringCentre(r, state.width, state.height);
      const dx = px - centre.x;
      const dy = py - centre.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < RING_RADII[r]) {
        const score = RING_SCORES[r];
        if (score > hitRing) hitRing = score as 1 | 3 | 5;
      }
    }
  }

  return { lane, skips: skipCount, hitRing, path };
}

/* ─── input ─────────────────────────────────────────────────────────────── */

export interface FjordInput {
  /** −1 / +1 lane shift, or null. */
  laneDelta: -1 | 0 | 1;
  /** Direct pointer-selected lane, or null for keyboard-only input. */
  targetLane?: AimLane | null;
  /** True while charge is held. */
  chargeHeld: boolean;
  /** Edge: charge just released this frame. */
  chargeReleased: boolean;
  /** Enter or Space (start / retry — NOT throw). */
  start: boolean;
  /** Escape (host owns). */
  exit: boolean;
}

/* ─── step ──────────────────────────────────────────────────────────────── */

/**
 * Advance one fixed timestep. Pure: returns a new state (shallow-immutable).
 */
export function stepFjordSkip(
  state: FjordSkipState,
  dt: number,
  input: FjordInput,
  rng: () => number,
): FjordSkipState {
  // Exit always honoured by host; logic just marks the phase for completeness.
  if (input.exit) {
    return { ...state, phase: "roundover" };
  }

  // Ready → start on Enter / pointer-press; first throw begins aiming.
  if (state.phase === "ready") {
    if (!input.start) return state;
    return beginThrow(state, rng);
  }

  // Roundover → retry on Enter.
  if (state.phase === "roundover") {
    if (input.start) return beginRound(state, rng);
    return state;
  }

  // Aiming: shift lane.
  if (state.phase === "aiming") {
    let next = { ...state };
    if (input.targetLane != null) {
      next.lane = input.targetLane;
    } else if (input.laneDelta !== 0) {
      const idx = LANE_INDICES.indexOf(state.lane);
      const newIdx = Math.max(
        0,
        Math.min(LANE_COUNT - 1, idx + input.laneDelta),
      );
      next.lane = LANE_INDICES[newIdx];
    }
    if (input.chargeHeld) {
      next = { ...next, phase: "charging", charge: 0 };
    }
    return next;
  }

  // Charging: accumulate charge while held.
  if (state.phase === "charging") {
    let next = { ...state };
    next.charge = Math.min(1, state.charge + dt * 1.6);
    if (input.chargeReleased || next.charge >= 1) {
      // Throw!
      if (state.reducedMotion) {
        // Reduced motion: resolve immediately with no path animation.
        const result = resolveSkip(next, next.charge, rng, true);
        const newResults = [...next.results, result];
        const newScore = next.score + result.hitRing;
        const isLast = next.throwIndex + 1 >= TOTAL_THROWS;
        return {
          ...next,
          phase: isLast ? "roundover" : "scored",
          score: newScore,
          results: newResults,
          throwIndex: next.throwIndex + 1,
          charge: 0,
        };
      }
      // Resolve the deterministic path once, then reveal it over time.
      next = {
        ...next,
        phase: "throwing",
        activeResult: resolveSkip(next, next.charge, rng, false),
        throwElapsed: 0,
      };
    }
    return next;
  }

  // Throwing: reveal the resolved path for a short, deterministic interval.
  if (state.phase === "throwing") {
    const throwElapsed = state.throwElapsed + Math.max(0, dt);
    if (throwElapsed < 0.65) return { ...state, throwElapsed };
    const result = state.activeResult;
    if (!result) return { ...state, phase: "aiming", throwElapsed: 0 };
    const newResults = [...state.results, result];
    const newScore = state.score + result.hitRing;
    const isLast = state.throwIndex + 1 >= TOTAL_THROWS;
    return {
      ...state,
      phase: isLast ? "roundover" : "scored",
      score: newScore,
      results: newResults,
      throwIndex: state.throwIndex + 1,
      charge: 0,
      activeResult: null,
      throwElapsed: 0,
    };
  }

  // Scored: begin the next throw and preserve this frame's input.
  if (state.phase === "scored") {
    return stepFjordSkip(beginThrow(state, rng), dt, input, rng);
  }

  return state;
}

/* ─── round / throw helpers ─────────────────────────────────────────────── */

function beginRound(state: FjordSkipState, rng: () => number): FjordSkipState {
  return {
    ...state,
    phase: "aiming",
    score: 0,
    throwIndex: 0,
    results: [],
    lane: 0,
    charge: 0,
    activeResult: null,
    throwElapsed: 0,
    current: (rng() - 0.5) * 2,
    currentSeed: Math.floor(rng() * 1_000_000),
  };
}

function beginThrow(state: FjordSkipState, rng: () => number): FjordSkipState {
  return {
    ...state,
    phase: "aiming",
    lane: 0,
    charge: 0,
    activeResult: null,
    throwElapsed: 0,
    // Re-roll current each throw for variety.
    current: (rng() - 0.5) * 2,
  };
}
