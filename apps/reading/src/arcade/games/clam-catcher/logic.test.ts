import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  clamCatcherWernerBeat,
  clamCatchStreakMultiplier,
  CLAM_CATCHER_TUNING,
  CLAM_MAX_STREAK,
  createClamCatcherState,
  startClamCatcher,
  stepClamCatcher,
  type ClamCatcherState,
} from "./logic";

const idle = { targetX: null, horizontal: 0 as const, start: false };

function run(seed: number): ClamCatcherState {
  const rng = createSeededRng(seed);
  let state = startClamCatcher(createClamCatcherState(320, 200));
  for (let frame = 0; frame < 600; frame += 1) {
    state = stepClamCatcher(
      state,
      1 / 60,
      { targetX: 40 + (frame % 240), horizontal: 0, start: false },
      rng,
    );
  }
  return state;
}

describe("Clam Catcher rules", () => {
  it("clamCatcherWernerBeat maps start, catch, and gameover living-TV edges", () => {
    expect(
      clamCatcherWernerBeat(
        { phase: "ready", score: 0, lives: 3 },
        { phase: "playing", score: 0, lives: 3 },
      ),
    ).toBe("highlight");
    expect(
      clamCatcherWernerBeat(
        { phase: "playing", score: 0, lives: 3 },
        { phase: "playing", score: 4, lives: 3 },
      ),
    ).toBe("piece_started");
    expect(
      clamCatcherWernerBeat(
        { phase: "playing", score: 4, lives: 1 },
        { phase: "gameover", score: 4, lives: 0 },
      ),
    ).toBe("fail");
  });

  it("is deterministic for a seed and scripted input", () => {
    expect(run(17)).toEqual(run(17));
    expect(run(17)).not.toEqual(run(18));
  });

  it("starts and restarts with a clean three-life shift", () => {
    const ready = createClamCatcherState(320, 200);
    const playing = stepClamCatcher(
      ready,
      1 / 60,
      { ...idle, start: true },
      () => 0.9,
    );
    expect(playing.phase).toBe("playing");
    expect(playing.lives).toBe(3);

    const restarted = stepClamCatcher(
      { ...playing, phase: "gameover", score: 99, lives: 0 },
      1 / 60,
      { ...idle, start: true },
      () => 0.9,
    );
    expect(restarted).toMatchObject({ phase: "playing", score: 0, lives: 3 });
    expect(restarted.entities).toEqual([]);
  });

  it("supports pointer positioning and bounded keyboard movement", () => {
    const base = {
      ...startClamCatcher(createClamCatcherState(320, 200)),
      spawnTimer: 99,
    };
    const pointer = stepClamCatcher(
      base,
      1 / 60,
      { targetX: 12, horizontal: 0, start: false },
      () => 0.9,
    );
    expect(pointer.bucketX).toBe(CLAM_CATCHER_TUNING.bucketWidth / 2);
    const keyboard = stepClamCatcher(
      pointer,
      0.05,
      { targetX: null, horizontal: 1, start: false },
      () => 0.9,
    );
    expect(keyboard.bucketX).toBeGreaterThan(pointer.bucketX);
  });

  it("scores both clam types and applies jellyfish loss in stable id order", () => {
    const base = startClamCatcher(createClamCatcherState(320, 200));
    const bucketY = base.height - 34;
    const state: ClamCatcherState = {
      ...base,
      lives: 1,
      spawnTimer: 99,
      entities: [
        {
          id: 3,
          kind: "pearl-clam",
          x: base.bucketX,
          y: bucketY,
          radius: 10,
          points: 4,
        },
        {
          id: 1,
          kind: "common-clam",
          x: base.bucketX,
          y: bucketY,
          radius: 9,
          points: 1,
        },
        {
          id: 2,
          kind: "jellyfish",
          x: base.bucketX,
          y: bucketY,
          radius: 13,
          points: 0,
        },
      ],
    };
    const next = stepClamCatcher(state, 0, idle, () => 0.9);
    expect(next.score).toBe(5);
    expect(next.lives).toBe(0);
    expect(next.phase).toBe("gameover");
    expect(next.entities).toEqual([]);
  });

  it("ramps fall speed and spawn cadence without crossing the floor", () => {
    const early = {
      ...startClamCatcher(createClamCatcherState(320, 200)),
      spawnTimer: 0,
    };
    const late = { ...early, elapsed: 200 };
    const earlyNext = stepClamCatcher(early, 0.05, idle, () => 0.9);
    const lateNext = stepClamCatcher(late, 0.05, idle, () => 0.9);
    expect(lateNext.spawnTimer).toBe(CLAM_CATCHER_TUNING.minimumSpawnSeconds);
    expect(earlyNext.spawnTimer).toBeGreaterThan(lateNext.spawnTimer);
  });

  it("caps long-session fall speed below the collision-tunneling floor", () => {
    const state: ClamCatcherState = {
      ...startClamCatcher(createClamCatcherState(320, 200)),
      elapsed: 10_000,
      spawnTimer: 99,
      entities: [
        { id: 1, kind: "common-clam", x: 40, y: 20, radius: 9, points: 1 },
      ],
    };
    const next = stepClamCatcher(state, 1 / 60, idle, () => 0.9);
    expect(next.entities[0]?.y).toBeCloseTo(
      20 + CLAM_CATCHER_TUNING.maximumFallSpeed / 60,
    );
    expect(CLAM_CATCHER_TUNING.maximumFallSpeed / 60).toBeLessThan(9);
  });

  it("builds Club Penguin–style catch-streak multiplier on consecutive good catches", () => {
    expect(clamCatchStreakMultiplier(0)).toBe(1);
    expect(clamCatchStreakMultiplier(1)).toBe(2);
    expect(clamCatchStreakMultiplier(CLAM_MAX_STREAK)).toBe(CLAM_MAX_STREAK);

    const base = startClamCatcher(createClamCatcherState(320, 200));
    const bucketY = base.height - 34;
    let s: ClamCatcherState = {
      ...base,
      spawnTimer: 99,
      entities: [
        {
          id: 1,
          kind: "common-clam",
          x: base.bucketX,
          y: bucketY,
          radius: 9,
          points: 1,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    expect(s.streak).toBe(1);
    expect(s.score).toBe(1); // mult 1×
    expect(s.maxStreak).toBe(1);

    s = {
      ...s,
      spawnTimer: 99,
      entities: [
        {
          id: 2,
          kind: "pearl-clam",
          x: s.bucketX,
          y: bucketY,
          radius: 10,
          points: 4,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    // Pearl jumps streak by two: 1 → 3 (cap), score still uses pre-step mult 2×.
    expect(s.streak).toBe(CLAM_MAX_STREAK);
    expect(s.score).toBe(1 + 4 * 2);
    expect(s.maxStreak).toBe(CLAM_MAX_STREAK);
  });

  it("pearl catch jumps streak by two without breaking the mult order", () => {
    const base = startClamCatcher(createClamCatcherState(320, 200));
    const bucketY = base.height - 34;
    let s: ClamCatcherState = {
      ...base,
      spawnTimer: 99,
      entities: [
        {
          id: 1,
          kind: "pearl-clam",
          x: base.bucketX,
          y: bucketY,
          radius: 10,
          points: 4,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    expect(s.score).toBe(4); // mult 1× on first pearl
    expect(s.streak).toBe(2); // pearl step +2
    expect(s.maxStreak).toBe(2);

    s = {
      ...s,
      spawnTimer: 99,
      entities: [
        {
          id: 2,
          kind: "common-clam",
          x: s.bucketX,
          y: bucketY,
          radius: 9,
          points: 1,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    expect(s.score).toBe(4 + 1 * 3); // mult 3× from streak 2
    expect(s.streak).toBe(CLAM_MAX_STREAK);
  });

  it("resets catch streak on jellyfish and on missed clam", () => {
    const base = startClamCatcher(createClamCatcherState(320, 200));
    const bucketY = base.height - 34;

    let s: ClamCatcherState = {
      ...base,
      streak: 2,
      maxStreak: 2,
      spawnTimer: 99,
      entities: [
        {
          id: 9,
          kind: "jellyfish",
          x: base.bucketX,
          y: bucketY,
          radius: 13,
          points: 0,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    expect(s.streak).toBe(0);
    expect(s.maxStreak).toBe(2);
    expect(s.lives).toBe(2);

    s = {
      ...s,
      streak: 3,
      maxStreak: 3,
      spawnTimer: 99,
      // Clam already past the floor (missed).
      entities: [
        {
          id: 10,
          kind: "common-clam",
          x: 40,
          y: s.height + 40,
          radius: 9,
          points: 1,
        },
      ],
    };
    s = stepClamCatcher(s, 0, idle, () => 0.9);
    expect(s.streak).toBe(0);
    expect(s.maxStreak).toBe(3);
    expect(s.entities).toEqual([]);
  });
});
