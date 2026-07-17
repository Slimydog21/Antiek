/**
 * Pure, fixed-step rules for Clam Catcher. Rendering and input sampling live elsewhere.
 *
 * Catch-streak densify (craft157+): consecutive good clam/pearl catches build a Club
 * Penguin–style multiplier (max 3×). Pearl catches jump the streak by two steps
 * (still capped) so the rare clam feels like a CP table reward. Jellyfish catch
 * or missed clam (falls past the floor) resets streak. Pure rules only — hosts
 * inject living-TV beats.
 */

export const CLAM_CATCHER_TUNING = Object.freeze({
  startingLives: 3,
  bucketWidth: 58,
  bucketHeight: 14,
  bucketSpeed: 360,
  openingFallSpeed: 74,
  /** Reaches a brisk but readable +72 px/s after two minutes. */
  fallSpeedRampPerSecond: 0.6,
  /** At 60 Hz this moves <4 px/frame, safely below the smallest catch body. */
  maximumFallSpeed: 220,
  openingSpawnSeconds: 1.05,
  /** Tightens toward the 0.34 s floor without producing spawn storms. */
  spawnRampPerSecond: 0.006,
  minimumSpawnSeconds: 0.34,
  commonPoints: 1,
  pearlPoints: 4,
  /** One fifth of seeded spawns are hazards; enough to demand lateral choices. */
  jellyfishChance: 0.2,
  pearlChance: 0.2,
} as const);

/** Max Club Penguin–style catch-streak multiplier (hard to vary). */
export const CLAM_MAX_STREAK = 3;

export type CatcherPhase = "ready" | "playing" | "gameover";
export type FallingKind = "common-clam" | "pearl-clam" | "jellyfish";

export interface FallingEntity {
  id: number;
  kind: FallingKind;
  x: number;
  y: number;
  radius: number;
  points: number;
}

export interface ClamCatcherState {
  phase: CatcherPhase;
  score: number;
  lives: number;
  bucketX: number;
  entities: FallingEntity[];
  elapsed: number;
  spawnTimer: number;
  nextEntityId: number;
  width: number;
  height: number;
  /** Consecutive good-catch streak for score multiplier (0 = none). */
  streak: number;
  /** Peak streak this run (cabinet densify / brag). */
  maxStreak: number;
}

export interface CatcherInput {
  targetX: number | null;
  horizontal: -1 | 0 | 1;
  start: boolean;
}

/** Catch-streak multiplier from consecutive good catches (1×..CLAM_MAX_STREAK). */
export function clamCatchStreakMultiplier(streak: number): number {
  if (!Number.isFinite(streak) || streak <= 0) return 1;
  return Math.min(CLAM_MAX_STREAK, 1 + Math.floor(streak));
}

export function createClamCatcherState(
  width: number,
  height: number,
): ClamCatcherState {
  const safeWidth = Math.max(120, width);
  const safeHeight = Math.max(120, height);
  return {
    phase: "ready",
    score: 0,
    lives: CLAM_CATCHER_TUNING.startingLives,
    bucketX: safeWidth / 2,
    entities: [],
    elapsed: 0,
    spawnTimer: 0,
    nextEntityId: 1,
    width: safeWidth,
    height: safeHeight,
    streak: 0,
    maxStreak: 0,
  };
}

export function startClamCatcher(state: ClamCatcherState): ClamCatcherState {
  return {
    ...state,
    phase: "playing",
    score: 0,
    lives: CLAM_CATCHER_TUNING.startingLives,
    bucketX: state.width / 2,
    entities: [],
    elapsed: 0,
    spawnTimer: 0,
    streak: 0,
    maxStreak: 0,
  };
}

export function stepClamCatcher(
  state: ClamCatcherState,
  dtSec: number,
  input: CatcherInput,
  rng: () => number,
): ClamCatcherState {
  if (state.phase !== "playing") {
    return input.start ? startClamCatcher(state) : state;
  }

  const dt = Math.max(0, Math.min(dtSec, 0.05));
  const halfBucket = CLAM_CATCHER_TUNING.bucketWidth / 2;
  let bucketX = state.bucketX;
  if (input.targetX !== null) {
    bucketX = input.targetX;
  } else {
    bucketX += input.horizontal * CLAM_CATCHER_TUNING.bucketSpeed * dt;
  }
  bucketX = clamp(bucketX, halfBucket, state.width - halfBucket);

  let next: ClamCatcherState = {
    ...state,
    bucketX,
    elapsed: state.elapsed + dt,
    spawnTimer: state.spawnTimer - dt,
    entities: state.entities.map((entity) => ({
      ...entity,
      y:
        entity.y +
        Math.min(
          CLAM_CATCHER_TUNING.maximumFallSpeed,
          CLAM_CATCHER_TUNING.openingFallSpeed +
            state.elapsed * CLAM_CATCHER_TUNING.fallSpeedRampPerSecond,
        ) *
          dt,
    })),
  };

  if (next.spawnTimer <= 0) {
    next = spawnEntity(next, rng);
    next.spawnTimer = Math.max(
      CLAM_CATCHER_TUNING.minimumSpawnSeconds,
      CLAM_CATCHER_TUNING.openingSpawnSeconds -
        next.elapsed * CLAM_CATCHER_TUNING.spawnRampPerSecond,
    );
  }

  const bucketTop = next.height - 34;
  const remaining: FallingEntity[] = [];
  let score = next.score;
  let lives = next.lives;
  let streak = next.streak;
  let maxStreak = next.maxStreak;

  // Entity ids encode spawn order. Sorting makes simultaneous contacts explicit
  // and stable even if a future renderer changes array construction order.
  for (const entity of [...next.entities].sort((a, b) => a.id - b.id)) {
    const caught =
      entity.y + entity.radius >= bucketTop &&
      entity.y - entity.radius <=
        bucketTop + CLAM_CATCHER_TUNING.bucketHeight &&
      entity.x + entity.radius >= bucketX - halfBucket &&
      entity.x - entity.radius <= bucketX + halfBucket;

    if (caught) {
      if (entity.kind === "jellyfish") {
        lives -= 1;
        // Hazard catch resets Club Penguin catch-streak (hard to vary).
        streak = 0;
      } else {
        const mult = clamCatchStreakMultiplier(streak);
        score += entity.points * mult;
        // Pearl densify: rare clam jumps streak by two (still hard-capped).
        const step = entity.kind === "pearl-clam" ? 2 : 1;
        streak = Math.min(CLAM_MAX_STREAK, streak + step);
        maxStreak = Math.max(maxStreak, streak);
      }
    } else if (entity.y - entity.radius <= next.height) {
      remaining.push(entity);
    } else if (entity.kind !== "jellyfish") {
      // Missed clam/pearl past the floor resets streak; dodged jelly does not.
      streak = 0;
    }
  }

  return {
    ...next,
    score,
    lives,
    streak,
    maxStreak,
    entities: lives <= 0 ? [] : remaining,
    phase: lives <= 0 ? "gameover" : "playing",
  };
}

/**
 * Living-TV beat for Clam Catcher (Club Penguin wait game).
 * start → highlight; score up while playing → piece_started; gameover → fail.
 */
export type ClamCatcherWernerBeat =
  | "highlight"
  | "piece_started"
  | "fail"
  | null;

export function clamCatcherWernerBeat(
  prev: Pick<ClamCatcherState, "phase" | "score" | "lives">,
  next: Pick<ClamCatcherState, "phase" | "score" | "lives">,
): ClamCatcherWernerBeat {
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

function spawnEntity(
  state: ClamCatcherState,
  rng: () => number,
): ClamCatcherState {
  const roll = rng();
  const kind: FallingKind =
    roll < CLAM_CATCHER_TUNING.jellyfishChance
      ? "jellyfish"
      : roll <
          CLAM_CATCHER_TUNING.jellyfishChance + CLAM_CATCHER_TUNING.pearlChance
        ? "pearl-clam"
        : "common-clam";
  const radius = kind === "jellyfish" ? 13 : kind === "pearl-clam" ? 10 : 9;
  const x = radius + rng() * (state.width - radius * 2);
  return {
    ...state,
    nextEntityId: state.nextEntityId + 1,
    entities: [
      ...state.entities,
      {
        id: state.nextEntityId,
        kind,
        x,
        y: -radius,
        radius,
        points:
          kind === "pearl-clam"
            ? CLAM_CATCHER_TUNING.pearlPoints
            : kind === "common-clam"
              ? CLAM_CATCHER_TUNING.commonPoints
              : 0,
      },
    ],
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
