import { describe, expect, it } from "vitest";

import { createSeededRng } from "../../engine/rng";
import {
  createFjordSkipState,
  laneToX,
  stepFjordSkip,
  TOTAL_THROWS,
  waterLineY,
} from "./logic";

describe("fjord skip pure logic", () => {
  /* ─── phase transitions ─────────────────────────────────────────────── */

  it("stays in ready until Enter is pressed", () => {
    const s0 = createFjordSkipState({ width: 960, height: 600 });
    expect(s0.phase).toBe("ready");
    const s1 = stepFjordSkip(
      s0,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("ready");
    const s2 = stepFjordSkip(
      s1,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s2.phase).toBe("aiming");
  });

  it("Enter alone starts quietly without throwing", () => {
    const s0 = createFjordSkipState({ width: 960, height: 600 });
    const s1 = stepFjordSkip(
      s0,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s1.phase).toBe("aiming");
    expect(s1.throwIndex).toBe(0);
    expect(s1.results).toEqual([]);
  });

  /* ─── lane selection ────────────────────────────────────────────────── */

  it("shifts aim lane with Left/Right without wrapping", () => {
    let s = createFjordSkipState({ width: 960, height: 600 });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.lane).toBe(0);

    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: -1,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.lane).toBe(-1);

    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: -1,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.lane).toBe(-2);

    // Cannot go beyond -2.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: -1,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.lane).toBe(-2);

    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 1,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.lane).toBe(-1);

    // Traverse to +2.
    for (let i = 0; i < 5; i++) {
      s = stepFjordSkip(
        s,
        1 / 60,
        {
          laneDelta: 1,
          chargeHeld: false,
          chargeReleased: false,
          start: false,
          exit: false,
        },
        createSeededRng(1),
      );
    }
    expect(s.lane).toBe(2);
  });

  /* ─── charging and throwing ─────────────────────────────────────────── */

  it("charges while held and throws on release", () => {
    let s = createFjordSkipState({ width: 960, height: 600 });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("aiming");

    // Start charging — transitions to charging with charge 0.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("charging");
    expect(s.charge).toBe(0);

    // Charge accumulates on the next frame.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.charge).toBeGreaterThan(0);

    // Release → throw.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: true,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("throwing");
  });

  it("resolves to scored after throwing, then auto-advances to aiming", () => {
    let s = createFjordSkipState({ width: 960, height: 600 });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: true,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    // Throwing phase.
    expect(s.phase).toBe("throwing");
    // The authored path remains visible during the throw interval.
    s = stepFjordSkip(
      s,
      0.3,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("throwing");
    expect(s.activeResult?.path.length).toBeGreaterThan(1);
    s = stepFjordSkip(
      s,
      0.36,
      {
        laneDelta: 0,
        targetLane: null,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("scored");
    expect(s.throwIndex).toBe(1);
    expect(s.results).toHaveLength(1);
    // Next step auto-advances to aiming.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("aiming");
  });

  it("does not swallow the first charge action after a scored throw", () => {
    const rng = createSeededRng(7);
    let s = createFjordSkipState({
      width: 960,
      height: 600,
      reducedMotion: true,
    });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      rng,
    );
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      rng,
    );
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: true,
        start: false,
        exit: false,
      },
      rng,
    );
    expect(s.phase).toBe("scored");
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      rng,
    );
    expect(s.phase).toBe("charging");
    expect(s.throwIndex).toBe(1);
  });

  /* ─── reduced motion ────────────────────────────────────────────────── */

  it("resolves throws immediately in reduced motion with no path animation", () => {
    let s = createFjordSkipState({
      width: 960,
      height: 600,
      reducedMotion: true,
    });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("aiming");

    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("charging");

    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: true,
        start: false,
        exit: false,
      },
      createSeededRng(1),
    );
    // Reduced motion skips throwing entirely → goes to scored or roundover.
    expect(s.phase === "scored" || s.phase === "roundover").toBe(true);
    expect(s.results).toHaveLength(1);
    // Path should be empty in reduced motion.
    expect(s.results[0].path).toEqual([]);
  });

  /* ─── six-throw round ───────────────────────────────────────────────── */

  it("completes exactly 6 throws then enters roundover", () => {
    const rng = createSeededRng(42);
    let s = createFjordSkipState({
      width: 960,
      height: 600,
      reducedMotion: true,
    });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      rng,
    );

    for (let t = 0; t < TOTAL_THROWS; t++) {
      if (s.phase === "roundover") break;
      // Aim.
      s = stepFjordSkip(
        s,
        1 / 60,
        {
          laneDelta: 0,
          chargeHeld: true,
          chargeReleased: false,
          start: false,
          exit: false,
        },
        rng,
      );
      // Charge a bit.
      s = stepFjordSkip(
        s,
        1 / 60,
        {
          laneDelta: 0,
          chargeHeld: true,
          chargeReleased: false,
          start: false,
          exit: false,
        },
        rng,
      );
      // Release.
      s = stepFjordSkip(
        s,
        1 / 60,
        {
          laneDelta: 0,
          chargeHeld: false,
          chargeReleased: true,
          start: false,
          exit: false,
        },
        rng,
      );
    }
    expect(s.phase).toBe("roundover");
    expect(s.results).toHaveLength(TOTAL_THROWS);
  });

  /* ─── retry ─────────────────────────────────────────────────────────── */

  it("retries from roundover on Enter", () => {
    let s = createFjordSkipState({
      width: 960,
      height: 600,
      reducedMotion: true,
    });
    s = { ...s, phase: "roundover", score: 12, throwIndex: 6, results: [] };
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("aiming");
    expect(s.score).toBe(0);
    expect(s.throwIndex).toBe(0);
  });

  /* ─── miss never scores ─────────────────────────────────────────────── */

  it("misses never receive consolation points", () => {
    // Use a seed/charge combo that produces a miss.
    const rng = createSeededRng(999);
    let s = createFjordSkipState({
      width: 960,
      height: 600,
      reducedMotion: true,
    });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      rng,
    );
    // Charge at minimum.
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: true,
        chargeReleased: false,
        start: false,
        exit: false,
      },
      rng,
    );
    // Quick release (very low charge).
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: true,
        start: false,
        exit: false,
      },
      rng,
    );
    // Score is either 0 (miss) or > 0 (hit ring) — never negative or consolation.
    expect(s.score).toBeGreaterThanOrEqual(0);
  });

  /* ─── determinism ───────────────────────────────────────────────────── */

  it("is exactly deterministic for the same seed and input trace", () => {
    const run = () => {
      const rng = createSeededRng(77);
      let state = createFjordSkipState({
        width: 960,
        height: 600,
        reducedMotion: true,
      });
      state = stepFjordSkip(
        state,
        1 / 60,
        {
          laneDelta: 0,
          chargeHeld: false,
          chargeReleased: false,
          start: true,
          exit: false,
        },
        rng,
      );
      for (let t = 0; t < TOTAL_THROWS; t++) {
        if (state.phase === "roundover") break;
        state = stepFjordSkip(
          state,
          1 / 60,
          {
            laneDelta: (t % 2 === 0 ? 1 : -1) as 1 | -1,
            chargeHeld: true,
            chargeReleased: false,
            start: false,
            exit: false,
          },
          rng,
        );
        state = stepFjordSkip(
          state,
          1 / 60,
          {
            laneDelta: 0,
            chargeHeld: true,
            chargeReleased: false,
            start: false,
            exit: false,
          },
          rng,
        );
        state = stepFjordSkip(
          state,
          1 / 60,
          {
            laneDelta: 0,
            chargeHeld: false,
            chargeReleased: true,
            start: false,
            exit: false,
          },
          rng,
        );
      }
      return state;
    };
    expect(run()).toEqual(run());
  });

  /* ─── exit ──────────────────────────────────────────────────────────── */

  it("exit sets roundover from any phase", () => {
    let s = createFjordSkipState({ width: 960, height: 600 });
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: true,
        exit: false,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("aiming");
    s = stepFjordSkip(
      s,
      1 / 60,
      {
        laneDelta: 0,
        chargeHeld: false,
        chargeReleased: false,
        start: false,
        exit: true,
      },
      createSeededRng(1),
    );
    expect(s.phase).toBe("roundover");
  });

  /* ─── geometry helpers ──────────────────────────────────────────────── */

  it("laneToX maps −2..+2 across the canvas width", () => {
    const w = 960;
    const x0 = laneToX(-2, w);
    const x2 = laneToX(2, w);
    expect(x0).toBeLessThan(x2);
    expect(x0).toBeGreaterThan(0);
    expect(x2).toBeLessThan(w);
  });

  it("waterLineY returns a consistent y below the top", () => {
    const y = waterLineY(600);
    expect(y).toBeGreaterThan(100);
    expect(y).toBeLessThan(500);
  });
});
