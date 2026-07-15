import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  CLAM_CATCHER_TUNING,
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
});
