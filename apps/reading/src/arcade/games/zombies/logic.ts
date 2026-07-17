/**
 * Paperclip Zombies — pure rules (BO1 arcade zombies–inspired wait easter egg).
 *
 * Endless waves of office-supply "zombies" march toward Werner's fort.
 * Click / fire to destroy them. Survive waves; lives deplete on breach.
 * Designed for deep-research wait states — endless loop with explicit exit.
 *
 * Combo densify (craft157+): consecutive kills build a BO1-style multiplier
 * (max 4×). Miss fire or fort breach resets combo. Wave-clear fort heal densify
 * (craft157+): clearing a wave restores +1 fort life, hard-capped at starting
 * lives (BO1-style fort repair). Pure rules only — hosts inject living-TV
 * beats; no product reaction-bus import in arcade core.
 */

export type ZombiesPhase = "ready" | "playing" | "gameover" | "exited";

/** Max BO1-style combo multiplier (hard to vary). */
export const ZOMBIES_MAX_COMBO = 4;

export interface Zombie {
  id: number;
  x: number;
  y: number;
  hp: number;
  speed: number;
  w: number;
  h: number;
}

export interface ZombiesState {
  phase: ZombiesPhase;
  score: number;
  lives: number;
  startingLives: number;
  wave: number;
  zombies: Zombie[];
  spawnRemaining: number;
  spawnTimer: number;
  elapsed: number;
  nextId: number;
  width: number;
  height: number;
  fortX: number;
  reducedMotion: boolean;
  /** Consecutive kill streak for combo multiplier (0 = none). */
  combo: number;
  /** Peak combo reached this run (cabinet brag / densify). */
  maxCombo: number;
}

export function createZombiesState(opts: {
  width: number;
  height: number;
  lives?: number;
  reducedMotion?: boolean;
}): ZombiesState {
  const startingLives = Math.max(1, Math.floor(opts.lives ?? 3));
  return {
    phase: "ready",
    score: 0,
    lives: startingLives,
    startingLives,
    wave: 0,
    zombies: [],
    spawnRemaining: 0,
    spawnTimer: 0,
    elapsed: 0,
    nextId: 1,
    width: Math.max(64, opts.width),
    height: Math.max(64, opts.height),
    fortX: 28,
    reducedMotion: Boolean(opts.reducedMotion),
    combo: 0,
    maxCombo: 0,
  };
}

export function startZombies(state: ZombiesState): ZombiesState {
  return beginWave(
    {
      ...state,
      phase: "playing",
      score: 0,
      lives: state.startingLives,
      wave: 0,
      zombies: [],
      elapsed: 0,
      nextId: 1,
      combo: 0,
      maxCombo: 0,
    },
    1,
  );
}

/** Combo multiplier from consecutive kills (1×..ZOMBIES_MAX_COMBO). */
export function zombiesComboMultiplier(combo: number): number {
  if (!Number.isFinite(combo) || combo <= 0) return 1;
  return Math.min(ZOMBIES_MAX_COMBO, 1 + Math.floor(combo));
}

function beginWave(state: ZombiesState, wave: number): ZombiesState {
  const count = 4 + wave * 2;
  // Fort heal densify: wave clears after wave 1 restore +1 life (cap at start).
  const lives =
    wave > 1
      ? Math.min(state.startingLives, state.lives + 1)
      : state.lives;
  return {
    ...state,
    wave,
    lives,
    spawnRemaining: count,
    spawnTimer: 0.2,
    zombies: [],
  };
}

export interface ZombiesInput {
  fireAt: { x: number; y: number } | null;
  start: boolean;
  exit: boolean;
}

function hitTest(z: Zombie, x: number, y: number): boolean {
  return x >= z.x && x <= z.x + z.w && y >= z.y && y <= z.y + z.h;
}

export function stepZombies(
  state: ZombiesState,
  dt: number,
  input: ZombiesInput,
  rng: () => number,
): ZombiesState {
  if (input.exit) {
    return { ...state, phase: "exited", zombies: [] };
  }
  if (state.phase === "ready") {
    if (input.start || input.fireAt) return startZombies(state);
    return state;
  }
  if (state.phase === "gameover" || state.phase === "exited") {
    if (input.start) return startZombies(state);
    return state;
  }

  let next: ZombiesState = {
    ...state,
    elapsed: state.elapsed + dt,
    zombies: state.zombies.map((z) => ({ ...z })),
  };

  // Fire
  if (input.fireAt) {
    const { x, y } = input.fireAt;
    const remaining: Zombie[] = [];
    let scored = false;
    let kill = false;
    for (const z of next.zombies) {
      if (!scored && hitTest(z, x, y)) {
        z.hp -= 1;
        scored = true;
        if (z.hp <= 0) {
          kill = true;
          const mult = zombiesComboMultiplier(next.combo);
          next.score += (10 + next.wave) * mult;
          next.combo = Math.min(ZOMBIES_MAX_COMBO, next.combo + 1);
          next.maxCombo = Math.max(next.maxCombo, next.combo);
          continue;
        }
      }
      remaining.push(z);
    }
    next.zombies = remaining;
    // Miss (or hit without kill that was only a chip): combo resets on full miss.
    if (!scored) {
      next.combo = 0;
      // Reduced-motion: each click also grants a point if miss (gentle)
      if (next.reducedMotion) next.score += 1;
    } else if (!kill && !next.reducedMotion) {
      // Chip hit without kill does not grow combo, but does not hard-reset —
      // keeps pressure on multi-HP paperclips without punishing aim.
    }
  }

  if (!next.reducedMotion) {
    next.spawnTimer -= dt;
    if (next.spawnRemaining > 0 && next.spawnTimer <= 0) {
      const y = 20 + rng() * (next.height - 50);
      next.zombies.push({
        id: next.nextId++,
        x: next.width - 20,
        y,
        hp: 1 + Math.floor(next.wave / 3),
        speed: 30 + next.wave * 4 + rng() * 20,
        w: 18,
        h: 18,
      });
      next.spawnRemaining -= 1;
      next.spawnTimer = Math.max(0.25, 0.9 - next.wave * 0.04);
    }

    const still: Zombie[] = [];
    let breached = false;
    for (const z of next.zombies) {
      z.x -= z.speed * dt;
      if (z.x <= next.fortX) {
        next.lives -= 1;
        breached = true;
      } else {
        still.push(z);
      }
    }
    next.zombies = still;
    // Fort breach resets combo (BO1-style run pressure).
    if (breached) next.combo = 0;
  } else {
    // Static simplified: no march; waves complete on score thresholds
    if (next.score >= next.wave * 20 + 20) {
      next = beginWave(next, next.wave + 1);
    }
  }

  if (next.lives <= 0) {
    next.phase = "gameover";
    next.zombies = [];
    return next;
  }

  // Wave clear → next wave
  if (
    !next.reducedMotion &&
    next.spawnRemaining === 0 &&
    next.zombies.length === 0
  ) {
    next = beginWave(next, next.wave + 1);
  }

  return next;
}

/** Endless-loop contract: playing never auto-ends without lives or exit. */
export function zombiesCanExit(state: ZombiesState): boolean {
  return state.phase === "playing" || state.phase === "gameover";
}

/**
 * Living-TV beat for a zombies step (pure). Wire to emitWernerExperience at
 * the cartridge edge so wait-arcade feels like the penguin TV show.
 *
 * - ready → playing: highlight (curious opt-in)
 * - wave advanced while playing: piece_started (happy craft / fort heal)
 * - kill score up while playing: piece_started (combo craft densify)
 * - playing → gameover: fail (dizzy)
 */
export type ZombiesWernerBeat =
  | "highlight"
  | "piece_started"
  | "fail"
  | null;

export function zombiesWernerBeat(
  prev: Pick<ZombiesState, "phase" | "wave" | "lives" | "score">,
  next: Pick<ZombiesState, "phase" | "wave" | "lives" | "score">,
): ZombiesWernerBeat {
  if (prev.phase === "ready" && next.phase === "playing") return "highlight";
  if (prev.phase === "playing" && next.phase === "gameover") return "fail";
  if (
    prev.phase === "playing" &&
    next.phase === "playing" &&
    next.wave > prev.wave
  ) {
    return "piece_started";
  }
  // Combo densify: each kill scores → happy craft beat (living-TV mid-run).
  if (
    prev.phase === "playing" &&
    next.phase === "playing" &&
    next.score > prev.score
  ) {
    return "piece_started";
  }
  return null;
}
