import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  createIceFishingState,
  iceFishingOverlapsHook,
  startRound,
  stepIceFishing,
  type IceFishingState,
} from "./logic";

describe("ice fishing pure logic", () => {
  it("starts and casts from ready in the same explicit drop action", () => {
    const s0 = createIceFishingState({ width: 200, height: 160 });
    expect(s0.phase).toBe("ready");
    const s1 = stepIceFishing(
      s0,
      1 / 60,
      { aimX: 100, drop: true, reel: false, start: false },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("playing");
    expect(s1.dropping).toBe(true);
    expect(s1.hookVy).toBe(140);
  });

  it("starts a quiet round from ready when Enter is pressed alone", () => {
    const s0 = createIceFishingState({ width: 200, height: 160 });
    const s1 = stepIceFishing(
      s0,
      1 / 60,
      { aimX: null, drop: false, reel: false, start: true },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("playing");
    expect(s1.dropping).toBe(false);
    expect(s1.hookY).toBe(36);
  });

  it("starts and resolves the first reduced-motion cast in one action", () => {
    const s0 = createIceFishingState({
      width: 200,
      height: 160,
      reducedMotion: true,
    });
    const s1 = stepIceFishing(
      s0,
      1 / 60,
      { aimX: 100, drop: true, reel: false, start: false },
      () => 0.8,
    );
    expect(s1.phase).toBe("playing");
    expect(s1.score).toBe(3);
  });

  it("spawns fish deterministically for a seed", () => {
    let s = startRound(createIceFishingState({ width: 240, height: 180 }));
    const rngA = createSeededRng(42);
    const rngB = createSeededRng(42);
    for (let i = 0; i < 120; i++) {
      s = stepIceFishing(
        s,
        1 / 60,
        { aimX: 120, drop: false, reel: false, start: false },
        rngA,
      );
    }
    const scoreA = s.score;
    const countA = s.fishes.length;

    let s2 = startRound(createIceFishingState({ width: 240, height: 180 }));
    for (let i = 0; i < 120; i++) {
      s2 = stepIceFishing(
        s2,
        1 / 60,
        { aimX: 120, drop: false, reel: false, start: false },
        rngB,
      );
    }
    expect(s2.fishes.length).toBe(countA);
    expect(s2.score).toBe(scoreA);
    expect(countA).toBeGreaterThan(0);
  });

  it("scores a catch when hook overlaps a fish while dropping", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      // Keep spawnTimer high so this step does not inject a new fish.
      spawnTimer: 99,
      fishes: [
        {
          id: 1,
          x: 45,
          y: 75,
          vx: 0,
          w: 20,
          h: 12,
          points: 3,
          kind: "medium",
        },
      ],
    };
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.5,
    );
    expect(s.score).toBe(3);
    expect(s.fishes.some((f) => f.id === 1)).toBe(false);
    expect(s.reeling).toBe(true);
  });

  it("hazard fish costs a life and gameover at 0 lives", () => {
    let s = startRound(
      createIceFishingState({ width: 200, height: 160, lives: 1 }),
    );
    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      fishes: [
        {
          id: 1,
          x: 45,
          y: 75,
          vx: 0,
          w: 20,
          h: 12,
          points: -1,
          kind: "hazard",
        },
      ],
    };
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.5,
    );
    expect(s.lives).toBe(0);
    expect(s.phase).toBe("gameover");
  });

  it("reduced-motion path resolves fish and boot encounters without involuntary spawn", () => {
    let s = startRound(
      createIceFishingState({
        width: 200,
        height: 160,
        reducedMotion: true,
      }),
    );
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 100, drop: true, reel: false, start: false },
      () => 0.8,
    );
    expect(s.score).toBe(3);
    expect(s.fishes).toEqual([]);

    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 100, drop: true, reel: false, start: false },
      () => 0.1,
    );
    expect(s.lives).toBe(2);
    expect(s.score).toBe(3);
  });

  it("does not add the reduced-motion miss bonus to a real catch", () => {
    const fish = {
      id: 1,
      x: 45,
      y: 75,
      vx: 0,
      w: 20,
      h: 12,
      points: -1,
      kind: "hazard" as const,
    };
    let state: IceFishingState = {
      ...startRound(
        createIceFishingState({
          width: 200,
          height: 160,
          lives: 2,
          reducedMotion: true,
        }),
      ),
      hookX: 50,
      hookY: 80,
      fishes: [fish],
    };
    expect(iceFishingOverlapsHook(state, fish)).toBe(true);
    state = stepIceFishing(
      state,
      1 / 60,
      { aimX: 50, drop: true, reel: false, start: false },
      () => 0.5,
    );
    expect(state.lives).toBe(1);
    expect(state.score).toBe(0);
  });

  it("preserves configured lives across game-over restart", () => {
    const gameOver = {
      ...startRound(
        createIceFishingState({ width: 200, height: 160, lives: 5 }),
      ),
      phase: "gameover" as const,
      lives: 0,
      score: 9,
    };
    const restarted = stepIceFishing(
      gameOver,
      1 / 60,
      { aimX: null, drop: false, reel: false, start: true },
      createSeededRng(3),
    );
    expect(restarted.phase).toBe("playing");
    expect(restarted.lives).toBe(5);
    expect(restarted.score).toBe(0);
  });

  it("is exactly deterministic for the same seed and input trace", () => {
    const run = () => {
      let state = createIceFishingState({ width: 260, height: 180 });
      const rng = createSeededRng(19);
      for (let frame = 0; frame < 240; frame++) {
        state = stepIceFishing(
          state,
          1 / 60,
          {
            aimX: 30 + (frame % 180),
            drop: frame % 53 === 0,
            reel: frame % 71 === 0,
            start: frame === 0,
          },
          rng,
        );
      }
      return state;
    };
    expect(run()).toEqual(run());
  });
});
