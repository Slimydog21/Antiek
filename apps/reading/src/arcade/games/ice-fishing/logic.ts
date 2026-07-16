/**
 * Ice Fishing — pure rules (Club Penguin–inspired catch loop).
 *
 * Drop line → fish spawn / swim → catch when hook overlaps fish → score.
 * Headless and deterministic under a seeded RNG.
 */

export type IcePhase = "ready" | "playing" | "gameover";

export interface Fish {
  id: number;
  x: number;
  y: number;
  vx: number;
  w: number;
  h: number;
  points: number;
  kind: "small" | "medium" | "hazard";
}

export interface IceFishingState {
  phase: IcePhase;
  score: number;
  lives: number;
  startingLives: number;
  hookX: number;
  hookY: number;
  hookVy: number;
  dropping: boolean;
  reeling: boolean;
  fishes: Fish[];
  spawnTimer: number;
  elapsed: number;
  nextFishId: number;
  width: number;
  height: number;
  /** When true, no automatic motion (reduced-motion simplified path). */
  reducedMotion: boolean;
}

export interface IceFishingConfig {
  width: number;
  height: number;
  lives?: number;
  reducedMotion?: boolean;
}

export function createIceFishingState(cfg: IceFishingConfig): IceFishingState {
  const width = Math.max(64, cfg.width);
  const height = Math.max(64, cfg.height);
  const startingLives = Math.max(1, Math.floor(cfg.lives ?? 3));
  return {
    phase: "ready",
    score: 0,
    lives: startingLives,
    startingLives,
    hookX: width / 2,
    hookY: 36,
    hookVy: 0,
    dropping: false,
    reeling: false,
    fishes: [],
    spawnTimer: 0,
    elapsed: 0,
    nextFishId: 1,
    width,
    height,
    reducedMotion: Boolean(cfg.reducedMotion),
  };
}

export function startRound(state: IceFishingState): IceFishingState {
  return {
    ...state,
    phase: "playing",
    score: 0,
    lives: state.startingLives,
    hookY: 36,
    hookVy: 0,
    dropping: false,
    reeling: false,
    fishes: [],
    spawnTimer: 0,
    elapsed: 0,
  };
}

function aabb(
  ax: number,
  ay: number,
  aw: number,
  ah: number,
  bx: number,
  by: number,
  bw: number,
  bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
}

function spawnFish(state: IceFishingState, rng: () => number): IceFishingState {
  const roll = rng();
  const kind: Fish["kind"] =
    roll < 0.15 ? "hazard" : roll < 0.55 ? "small" : "medium";
  const fromLeft = rng() < 0.5;
  const y = 70 + rng() * (state.height - 110);
  const speed = 40 + rng() * 50 + Math.min(40, state.elapsed * 2);
  const w = kind === "medium" ? 28 : 18;
  const h = kind === "medium" ? 14 : 10;
  const points = kind === "hazard" ? -1 : kind === "medium" ? 3 : 1;
  const fish: Fish = {
    id: state.nextFishId,
    x: fromLeft ? -w : state.width + w,
    y,
    vx: fromLeft ? speed : -speed,
    w,
    h,
    points,
    kind,
  };
  return {
    ...state,
    nextFishId: state.nextFishId + 1,
    fishes: [...state.fishes, fish],
  };
}

export interface IceInput {
  /** Desired hook x (pointer or keyboard). */
  aimX: number | null;
  drop: boolean;
  reel: boolean;
  start: boolean;
}

/**
 * Advance one fixed step. Pure: returns a new state (shallow-immutable).
 */
export function stepIceFishing(
  state: IceFishingState,
  dt: number,
  input: IceInput,
  rng: () => number,
): IceFishingState {
  if (state.phase === "ready") {
    if (input.start || input.drop) return startRound(state);
    return state;
  }
  if (state.phase === "gameover") {
    if (input.start) return startRound(state);
    return state;
  }

  let next: IceFishingState = {
    ...state,
    elapsed: state.elapsed + dt,
    fishes: state.fishes.map((f) => ({ ...f })),
  };

  if (input.aimX !== null) {
    next.hookX = Math.max(12, Math.min(next.width - 12, input.aimX));
  }

  if (!next.reducedMotion) {
    if (input.drop && !next.dropping && !next.reeling) {
      next.dropping = true;
      next.hookVy = 140;
    }
    if (input.reel && (next.dropping || next.hookY > 36)) {
      next.reeling = true;
      next.dropping = false;
      next.hookVy = -180;
    }

    next.hookY += next.hookVy * dt;
    if (next.hookY <= 36) {
      next.hookY = 36;
      next.hookVy = 0;
      next.dropping = false;
      next.reeling = false;
    }
    if (next.hookY >= next.height - 16) {
      next.hookY = next.height - 16;
      next.hookVy = 0;
      next.dropping = false;
      next.reeling = true;
    }

    next.spawnTimer -= dt;
    if (next.spawnTimer <= 0) {
      next = spawnFish(next, rng);
      next.spawnTimer = Math.max(0.45, 1.4 - next.elapsed * 0.02);
    }

    next.fishes = next.fishes
      .map((f) => ({ ...f, x: f.x + f.vx * dt }))
      .filter((f) => f.x > -60 && f.x < next.width + 60);
  }

  // Catch check
  const hookSize = 10;
  const remaining: Fish[] = [];
  let caught = false;
  for (const f of next.fishes) {
    const hit = aabb(
      next.hookX - hookSize / 2,
      next.hookY - hookSize / 2,
      hookSize,
      hookSize,
      f.x,
      f.y,
      f.w,
      f.h,
    );
    if (hit && (next.dropping || next.reeling || next.reducedMotion)) {
      caught = true;
      if (f.kind === "hazard") {
        next.lives -= 1;
        next.reeling = true;
        next.dropping = false;
        next.hookVy = -200;
      } else {
        next.score += f.points;
        next.reeling = true;
        next.dropping = false;
        next.hookVy = -200;
      }
    } else {
      remaining.push(f);
    }
  }
  next.fishes = remaining;

  // Reduced-motion simplified path: click/start awards a point occasionally
  if (next.reducedMotion && input.drop && !caught) {
    next.score += 1;
  }

  if (next.lives <= 0) {
    next.phase = "gameover";
    next.fishes = [];
    next.dropping = false;
    next.reeling = false;
  }

  return next;
}

/**
 * Living-TV beat for ice fishing (Club Penguin wait game).
 * start → highlight; score up while playing → piece_started; gameover → fail.
 */
export type IceFishingWernerBeat =
  | "highlight"
  | "piece_started"
  | "fail"
  | null;

export function iceFishingWernerBeat(
  prev: Pick<IceFishingState, "phase" | "score" | "lives">,
  next: Pick<IceFishingState, "phase" | "score" | "lives">,
): IceFishingWernerBeat {
  if (prev.phase === "ready" && next.phase === "playing") return "highlight";
  if (prev.phase === "playing" && next.phase === "gameover") return "fail";
  if (
    prev.phase === "playing" &&
    next.phase === "playing" &&
    next.score > prev.score
  ) {
    return "piece_started";
  }
  return null;
}

export function iceFishingOverlapsHook(
  state: IceFishingState,
  fish: Fish,
): boolean {
  const hookSize = 10;
  return (
    state.hookX - hookSize / 2 < fish.x + fish.w &&
    state.hookX + hookSize / 2 > fish.x &&
    state.hookY - hookSize / 2 < fish.y + fish.h &&
    state.hookY + hookSize / 2 > fish.y
  );
}
