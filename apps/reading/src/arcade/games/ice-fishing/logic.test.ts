import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  createIceFishingState,
  iceCatchStreakMultiplier,
  iceFishingOverlapsHook,
  iceFishingWernerBeat,
  ICE_GOLDEN_POINTS,
  ICE_MAX_STREAK,
  startRound,
  stepIceFishing,
  type IceFishingState,
} from "./logic";

describe("ice fishing pure logic", () => {
  it("starts a round from ready on drop/start", () => {
    const s0 = createIceFishingState({ width: 200, height: 160 });
    expect(s0.phase).toBe("ready");
    const s1 = stepIceFishing(
      s0,
      1 / 60,
      { aimX: 100, drop: true, reel: false, start: false },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("playing");
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

  it("reduced-motion path awards on drop without requiring spawn", () => {
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
      () => 0.1,
    );
    expect(s.score).toBeGreaterThanOrEqual(1);
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

  it("iceFishingWernerBeat maps start, catch, and gameover living-TV edges", () => {
    expect(
      iceFishingWernerBeat(
        { phase: "ready", score: 0, lives: 3 },
        { phase: "playing", score: 0, lives: 3 },
      ),
    ).toBe("highlight");
    expect(
      iceFishingWernerBeat(
        { phase: "playing", score: 0, lives: 3 },
        { phase: "playing", score: 3, lives: 3 },
      ),
    ).toBe("piece_started");
    expect(
      iceFishingWernerBeat(
        { phase: "playing", score: 3, lives: 1 },
        { phase: "gameover", score: 3, lives: 0 },
      ),
    ).toBe("fail");
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

  it("builds Club Penguin–style catch-streak multiplier on consecutive good catches", () => {
    expect(iceCatchStreakMultiplier(0)).toBe(1);
    expect(iceCatchStreakMultiplier(1)).toBe(2);
    expect(iceCatchStreakMultiplier(ICE_MAX_STREAK)).toBe(ICE_MAX_STREAK);

    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
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
      () => 0.2,
    );
    expect(s.streak).toBe(1);
    expect(s.score).toBe(3); // mult 1×
    expect(s.maxStreak).toBe(1);

    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      spawnTimer: 99,
      fishes: [
        {
          id: 2,
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
      () => 0.2,
    );
    expect(s.streak).toBe(2);
    expect(s.score).toBe(3 + 3 * 2); // second catch 2×
  });

  it("spawns rare golden fish in the densify roll band", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    // spawnFish roll: hazard <0.15, golden <0.23 — pin first roll at 0.18.
    const rolls = [0.18, 0.2, 0.3];
    let i = 0;
    const rng = () => rolls[i++] ?? 0.5;
    s = {
      ...s,
      spawnTimer: 0,
      fishes: [],
    };
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 100, drop: false, reel: false, start: false },
      rng,
    );
    expect(s.fishes.some((f) => f.kind === "golden")).toBe(true);
    const golden = s.fishes.find((f) => f.kind === "golden");
    expect(golden?.points).toBe(ICE_GOLDEN_POINTS);
  });

  it("golden catch jumps streak by two without breaking the mult order", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      spawnTimer: 99,
      fishes: [
        {
          id: 1,
          x: 45,
          y: 75,
          vx: 0,
          w: 28,
          h: 14,
          points: ICE_GOLDEN_POINTS,
          kind: "golden",
        },
      ],
    };
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.2,
    );
    expect(s.score).toBe(ICE_GOLDEN_POINTS); // mult 1× on first golden
    expect(s.streak).toBe(2); // golden step +2
    expect(s.maxStreak).toBe(2);

    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      spawnTimer: 99,
      fishes: [
        {
          id: 2,
          x: 45,
          y: 75,
          vx: 0,
          w: 20,
          h: 12,
          points: 1,
          kind: "small",
        },
      ],
    };
    s = stepIceFishing(
      s,
      1 / 60,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.2,
    );
    expect(s.score).toBe(ICE_GOLDEN_POINTS + 1 * 3); // mult 3× from streak 2
    expect(s.streak).toBe(ICE_MAX_STREAK);
  });

  it("resets catch streak on hazard", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      dropping: true,
      hookX: 50,
      hookY: 80,
      streak: 2,
      maxStreak: 2,
      castHadCatch: false,
      spawnTimer: 99,
      fishes: [
        {
          id: 9,
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
      () => 0.2,
    );
    expect(s.streak).toBe(0);
    expect(s.maxStreak).toBe(2);
    expect(s.lives).toBeLessThan(3);
  });

  it("resets catch streak on empty cast returning to surface", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      reeling: true,
      dropping: false,
      hookX: 50,
      hookY: 40,
      hookVy: -180,
      streak: 2,
      maxStreak: 2,
      castHadCatch: false,
      spawnTimer: 99,
      fishes: [],
    };
    // One large step reels past the surface without a catch.
    s = stepIceFishing(
      s,
      0.1,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.2,
    );
    expect(s.hookY).toBe(36);
    expect(s.reeling).toBe(false);
    expect(s.streak).toBe(0);
    expect(s.maxStreak).toBe(2); // peak brag retained
  });

  it("keeps catch streak when a cast that caught returns to surface", () => {
    let s = startRound(createIceFishingState({ width: 200, height: 160 }));
    s = {
      ...s,
      reeling: true,
      dropping: false,
      hookX: 50,
      hookY: 40,
      hookVy: -180,
      streak: 2,
      maxStreak: 2,
      castHadCatch: true,
      spawnTimer: 99,
      fishes: [],
    };
    s = stepIceFishing(
      s,
      0.1,
      { aimX: 50, drop: false, reel: false, start: false },
      () => 0.2,
    );
    expect(s.hookY).toBe(36);
    expect(s.streak).toBe(2);
    expect(s.maxStreak).toBe(2);
  });
});
