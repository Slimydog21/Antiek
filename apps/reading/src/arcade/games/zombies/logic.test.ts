import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  createZombiesState,
  startZombies,
  stepZombies,
  zombiesCanExit,
  zombiesComboMultiplier,
  zombiesWernerBeat,
  ZOMBIES_MAX_COMBO,
} from "./logic";

describe("paperclip zombies pure logic", () => {
  it("starts on fire/start from ready", () => {
    const s0 = createZombiesState({ width: 320, height: 200 });
    const s1 = stepZombies(
      s0,
      1 / 60,
      { fireAt: { x: 10, y: 10 }, start: false, exit: false },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("playing");
    expect(s1.wave).toBe(1);
  });

  it("spawns a wave and advances when cleared", () => {
    let s = startZombies(createZombiesState({ width: 320, height: 200 }));
    expect(s.wave).toBe(1);
    // Instant-kill all by firing every zombie position after forcing spawn
    const rng = createSeededRng(7);
    for (let i = 0; i < 300; i++) {
      s = stepZombies(
        s,
        1 / 60,
        { fireAt: null, start: false, exit: false },
        rng,
      );
    }
    expect(s.zombies.length + s.spawnRemaining).toBeGreaterThan(0);
    // Kill whatever is on screen
    for (let guard = 0; guard < 50 && s.zombies.length > 0; guard++) {
      const z = s.zombies[0];
      s = stepZombies(
        s,
        1 / 60,
        {
          fireAt: { x: z.x + 2, y: z.y + 2 },
          start: false,
          exit: false,
        },
        rng,
      );
    }
    // Drain remaining spawns + kills
    for (let i = 0; i < 500; i++) {
      if (s.zombies[0]) {
        const z = s.zombies[0];
        s = stepZombies(
          s,
          1 / 60,
          {
            fireAt: { x: z.x + 2, y: z.y + 2 },
            start: false,
            exit: false,
          },
          rng,
        );
      } else {
        s = stepZombies(
          s,
          1 / 60,
          { fireAt: null, start: false, exit: false },
          rng,
        );
      }
      if (s.wave > 1) break;
    }
    expect(s.wave).toBeGreaterThan(1);
  });

  it("breach costs lives and gameover ends the loop", () => {
    let s = startZombies(
      createZombiesState({ width: 200, height: 120, lives: 1 }),
    );
    s = {
      ...s,
      spawnRemaining: 0,
      zombies: [
        {
          id: 1,
          x: s.fortX + 1,
          y: 40,
          hp: 1,
          speed: 500,
          w: 18,
          h: 18,
        },
      ],
    };
    s = stepZombies(
      s,
      1 / 30,
      { fireAt: null, start: false, exit: false },
      () => 0.5,
    );
    expect(s.lives).toBeLessThanOrEqual(0);
    expect(s.phase).toBe("gameover");
  });

  it("exit leaves endless loop cleanly", () => {
    let s = startZombies(createZombiesState({ width: 320, height: 200 }));
    expect(zombiesCanExit(s)).toBe(true);
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: null, start: false, exit: true },
      () => 0.1,
    );
    expect(s.phase).toBe("exited");
    expect(s.zombies).toEqual([]);
  });

  it("firing a zombie scores points", () => {
    let s = startZombies(createZombiesState({ width: 320, height: 200 }));
    s = {
      ...s,
      spawnRemaining: 0,
      zombies: [{ id: 1, x: 100, y: 50, hp: 1, speed: 0, w: 18, h: 18 }],
    };
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: { x: 105, y: 55 }, start: false, exit: false },
      () => 0.2,
    );
    expect(s.score).toBeGreaterThan(0);
    expect(s.zombies.length).toBe(0);
  });

  it("heals fort by one life on wave clear, hard-capped at starting lives", () => {
    let s = {
      ...startZombies(createZombiesState({ width: 320, height: 200 })),
      wave: 1,
      lives: 2,
      startingLives: 3,
      spawnRemaining: 0,
      zombies: [],
    };
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: null, start: false, exit: false },
      () => 0.2,
    );
    expect(s.wave).toBe(2);
    expect(s.lives).toBe(3); // +1 fort heal

    // Full fort does not overheal past starting lives.
    s = {
      ...s,
      spawnRemaining: 0,
      zombies: [],
    };
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: null, start: false, exit: false },
      () => 0.2,
    );
    expect(s.wave).toBe(3);
    expect(s.lives).toBe(3);
  });

  it("zombiesWernerBeat maps living-TV edges for start, wave, and gameover", () => {
    expect(
      zombiesWernerBeat(
        { phase: "ready", wave: 0, lives: 3 },
        { phase: "playing", wave: 1, lives: 3 },
      ),
    ).toBe("highlight");
    expect(
      zombiesWernerBeat(
        { phase: "playing", wave: 1, lives: 3 },
        { phase: "playing", wave: 2, lives: 3 },
      ),
    ).toBe("piece_started");
    expect(
      zombiesWernerBeat(
        { phase: "playing", wave: 2, lives: 1 },
        { phase: "gameover", wave: 2, lives: 0 },
      ),
    ).toBe("fail");
    expect(
      zombiesWernerBeat(
        { phase: "playing", wave: 2, lives: 2 },
        { phase: "playing", wave: 2, lives: 2 },
      ),
    ).toBeNull();
  });

  it("preserves configured lives across start and restart", () => {
    const configured = createZombiesState({
      width: 320,
      height: 200,
      lives: 5,
    });
    const started = startZombies(configured);
    expect(started.lives).toBe(5);
    const restarted = stepZombies(
      { ...started, phase: "gameover", lives: 0, score: 99 },
      1 / 60,
      { fireAt: null, start: true, exit: false },
      createSeededRng(4),
    );
    expect(restarted.lives).toBe(5);
    expect(restarted.score).toBe(0);
    expect(restarted.wave).toBe(1);
  });

  it("requires every hit point before scoring a kill", () => {
    let state = {
      ...startZombies(createZombiesState({ width: 320, height: 200 })),
      spawnRemaining: 1,
      zombies: [{ id: 1, x: 100, y: 50, hp: 2, speed: 0, w: 18, h: 18 }],
    };
    const fire = { fireAt: { x: 105, y: 55 }, start: false, exit: false };
    state = stepZombies(state, 1 / 60, fire, () => 0.2);
    expect(state.zombies[0]?.hp).toBe(1);
    expect(state.score).toBe(0);
    state = stepZombies(state, 1 / 60, fire, () => 0.2);
    expect(state.zombies).toHaveLength(0);
    expect(state.score).toBeGreaterThan(0);
  });

  it("is exactly deterministic for the same seed and input trace", () => {
    const run = () => {
      let state = createZombiesState({ width: 320, height: 200 });
      const rng = createSeededRng(23);
      for (let frame = 0; frame < 260; frame++) {
        const target = state.zombies[0];
        state = stepZombies(
          state,
          1 / 60,
          {
            fireAt:
              frame % 11 === 0 && target
                ? { x: target.x + 2, y: target.y + 2 }
                : null,
            start: frame === 0,
            exit: false,
          },
          rng,
        );
      }
      return state;
    };
    expect(run()).toEqual(run());
  });

  it("builds BO1-style combo multiplier on consecutive kills", () => {
    expect(zombiesComboMultiplier(0)).toBe(1);
    expect(zombiesComboMultiplier(1)).toBe(2);
    expect(zombiesComboMultiplier(ZOMBIES_MAX_COMBO)).toBe(ZOMBIES_MAX_COMBO);
    expect(zombiesComboMultiplier(99)).toBe(ZOMBIES_MAX_COMBO);

    let s = startZombies(createZombiesState({ width: 320, height: 200 }));
    s = {
      ...s,
      spawnRemaining: 0,
      zombies: [
        { id: 1, x: 100, y: 50, hp: 1, speed: 0, w: 18, h: 18 },
        { id: 2, x: 140, y: 50, hp: 1, speed: 0, w: 18, h: 18 },
      ],
    };
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: { x: 105, y: 55 }, start: false, exit: false },
      () => 0.2,
    );
    expect(s.combo).toBe(1);
    expect(s.maxCombo).toBe(1);
    const afterFirst = s.score;
    const waveAtSecondKill = s.wave;
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: { x: 145, y: 55 }, start: false, exit: false },
      () => 0.2,
    );
    // Combo grows; wave may advance after clear — score uses pre-clear wave.
    expect(s.combo).toBe(2);
    expect(s.score - afterFirst).toBe((10 + waveAtSecondKill) * 2);
  });

  it("resets combo on miss fire and on fort breach", () => {
    let s = startZombies(createZombiesState({ width: 320, height: 200 }));
    s = {
      ...s,
      spawnRemaining: 0,
      combo: 3,
      maxCombo: 3,
      zombies: [{ id: 1, x: 100, y: 50, hp: 1, speed: 0, w: 18, h: 18 }],
    };
    s = stepZombies(
      s,
      1 / 60,
      { fireAt: { x: 1, y: 1 }, start: false, exit: false },
      () => 0.2,
    );
    expect(s.combo).toBe(0);
    expect(s.maxCombo).toBe(3);

    s = {
      ...s,
      combo: 2,
      spawnRemaining: 0,
      zombies: [
        {
          id: 9,
          x: s.fortX + 1,
          y: 40,
          hp: 1,
          speed: 500,
          w: 18,
          h: 18,
        },
      ],
    };
    s = stepZombies(
      s,
      1 / 30,
      { fireAt: null, start: false, exit: false },
      () => 0.5,
    );
    expect(s.combo).toBe(0);
  });
});
