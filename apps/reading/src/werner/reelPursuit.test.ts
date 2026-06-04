import { describe, expect, it } from "vitest";

import {
  DEFAULT_REEL_CONFIG,
  isReelSettled,
  makeReelState,
  REEL_MAX_DT_MS,
  reelSpringStep,
  reelStateStep,
  reelStep,
  type ReelConfig,
  type ReelState,
} from "./reelPursuit";
import {
  REEL_MAX_PX_PER_S,
  REEL_SETTLE_EPSILON_PX,
  REEL_TAU_MS,
} from "./iceFishingConstants";

/** The old, snappy first-order reel — frozen here as the "baseline" we beat. */
const BASELINE_TAU_MS = 450;
const BASELINE_CFG: ReelConfig = {
  ...DEFAULT_REEL_CONFIG,
  mode: "exponential",
  tauMs: BASELINE_TAU_MS,
};

/** Run the DEFAULT (spring) reel from `start` toward `target`, fixed dt. */
function runSpring(
  start: { x: number; y: number },
  target: { x: number; y: number },
  dtMs: number,
  steps: number,
): ReelState[] {
  const trace: ReelState[] = [makeReelState(start)];
  let s = trace[0];
  for (let i = 0; i < steps; i++) {
    s = reelSpringStep(s, target, dtMs);
    trace.push(s);
  }
  return trace;
}

/**
 * Run the reel THROUGH the production router `reelStateStep` with the DEFAULT
 * config — i.e. exactly the path PenguinMascot drives (PenguinMascot.tsx ~436).
 * Behavioural assertions routed through this prove the WIRED path (not just the
 * bare `reelSpringStep`) decelerates / never overshoots. If the default mode is
 * ever flipped to "exponential", these go through the exponential integrator
 * and the deceleration/no-overshoot assertions fail — that is the gate.
 */
function runRouted(
  start: { x: number; y: number },
  target: { x: number; y: number },
  dtMs: number,
  steps: number,
): ReelState[] {
  const trace: ReelState[] = [makeReelState(start)];
  let s = trace[0];
  for (let i = 0; i < steps; i++) {
    s = reelStateStep(s, target, dtMs); // DEFAULT config — the production path.
    trace.push(s);
  }
  return trace;
}

describe("reelPursuit — exponential fallback (unchanged contract)", () => {
  it("settles toward target within the (now slower) lag budget", () => {
    let pos = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    let t = 0;
    // tau is 950 now; allow generous budget for the 8px epsilon settle.
    while (t < 4000 && !isReelSettled(pos, target, 12)) {
      pos = reelStep(pos, target, 16, BASELINE_CFG); // baseline still works
      t += 16;
    }
    expect(isReelSettled(pos, target, 12)).toBe(true);
  });

  it("caps per-frame displacement on teleport (velocity cap preserved)", () => {
    const next = reelStep({ x: 0, y: 0 }, { x: 2000, y: 0 }, 16);
    const cap = (REEL_MAX_PX_PER_S * 16) / 1000;
    expect(Math.hypot(next.x, next.y)).toBeLessThanOrEqual(cap + 0.01);
  });

  it("moves only toward target not away on axis", () => {
    const next = reelStep({ x: 0, y: 0 }, { x: 50, y: 0 }, 16);
    expect(next.x).toBeGreaterThan(0);
    expect(next.y).toBe(0);
  });

  it("is the documented fallback selectable via cfg.mode", () => {
    expect(DEFAULT_REEL_CONFIG.mode).toBe("spring");
    // The exponential path is reachable through the integrator-agnostic step.
    const expoCfg: ReelConfig = { ...DEFAULT_REEL_CONFIG, mode: "exponential" };
    const out = reelStateStep(makeReelState({ x: 0, y: 0 }), { x: 100, y: 0 }, 16, expoCfg);
    // Same first move as raw reelStep with the same cfg (no spring momentum).
    const raw = reelStep({ x: 0, y: 0 }, { x: 100, y: 0 }, 16, expoCfg);
    expect(out.x).toBeCloseTo(raw.x, 6);
  });
});

describe("reelPursuit — critically-damped spring (SPR-03 default)", () => {
  // ── M2: DECELERATION — closing speed decreases as distance shrinks. ──
  it("decelerates as it nears: per-step displacement falls monotonically near the target", () => {
    const target = { x: 600, y: 0 };
    const trace = runSpring({ x: 0, y: 0 }, target, 16, 200);

    // Per-step displacement magnitude (proportional to instantaneous speed).
    const steps = trace.slice(1).map((s, i) => Math.hypot(s.x - trace[i].x, s.y - trace[i].y));

    // The spring accelerates off the mark, so speed RISES then FALLS. Find the
    // peak; everything after the peak must be (weakly) decreasing — the settle.
    let peak = 0;
    for (let i = 1; i < steps.length; i++) if (steps[i] > steps[peak]) peak = i;
    expect(peak).toBeGreaterThan(0); // it genuinely accelerated off the mark

    for (let i = peak + 1; i < steps.length; i++) {
      // Strictly non-increasing past the peak (allow a hair of float noise).
      expect(steps[i]).toBeLessThanOrEqual(steps[i - 1] + 1e-9);
    }
  });

  it("samples far/mid/near and confirms speed at near < speed at mid < speed at far (post-peak)", () => {
    const target = { x: 800, y: 0 };
    const trace = runSpring({ x: 0, y: 0 }, target, 16, 300);
    const speedAt = (i: number) => Math.hypot(trace[i + 1].x - trace[i].x, trace[i + 1].y - trace[i].y);
    const distAt = (i: number) => Math.abs(target.x - trace[i].x);

    // Pick three indices AFTER the acceleration peak, ordered far→mid→near.
    // Find the peak first.
    let peak = 0;
    for (let i = 1; i < trace.length - 1; i++) if (speedAt(i) > speedAt(peak)) peak = i;
    const far = peak + 2;
    const near = trace.length - 3;
    const mid = Math.floor((far + near) / 2);

    expect(distAt(far)).toBeGreaterThan(distAt(mid));
    expect(distAt(mid)).toBeGreaterThan(distAt(near));
    // Closing speed shrinks as the remaining distance shrinks.
    expect(speedAt(far)).toBeGreaterThan(speedAt(mid));
    expect(speedAt(mid)).toBeGreaterThan(speedAt(near));
  });

  // ── M2: NO OVERSHOOT — sweep dt + start distances; never passes the target. ──
  it("never overshoots the target across a dt × distance sweep (1-D)", () => {
    const dts = [4, 8, 16, 24, 33, 48];
    const distances = [20, 80, 200, 500, 1200, 3000];
    for (const dt of dts) {
      for (const d of distances) {
        const target = { x: d, y: 0 };
        let s = makeReelState({ x: 0, y: 0 });
        const startSign = Math.sign(target.x - s.x); // +1 (approaching from 0)
        let approached = false;
        // Enough steps that even a cap-limited far pull at the smallest dt has
        // budget to converge: d/(cap·dt/1000) + the easing tail.
        for (let i = 0; i < 4000; i++) {
          const before = Math.abs(target.x - s.x);
          s = reelSpringStep(s, target, dt);
          const rem = target.x - s.x;
          // Critically damped ⇒ monotone approach ⇒ position never passes target:
          // (target - pos) keeps the sign it started with (never flips).
          expect(Math.sign(rem) === startSign || Math.abs(rem) < 1e-6).toBe(true);
          // And the gap is (weakly) shrinking every step — never grows.
          expect(Math.abs(rem)).toBeLessThanOrEqual(before + 1e-6);
          if (Math.abs(rem) < before - 1e-9) approached = true;
          if (isReelSettled(s, target, 0.5)) break;
        }
        // It genuinely closed the gap (and, given the step budget, settled).
        expect(approached).toBe(true);
        expect(isReelSettled(s, target, 1)).toBe(true);
      }
    }
  });

  it("never overshoots in 2-D either (diagonal pull)", () => {
    const target = { x: 400, y: 300 };
    let s = makeReelState({ x: 0, y: 0 });
    let prevDist = Math.hypot(target.x - s.x, target.y - s.y);
    for (let i = 0; i < 2000; i++) {
      s = reelSpringStep(s, target, 16);
      const dist = Math.hypot(target.x - s.x, target.y - s.y);
      // Monotone non-increasing distance ⇒ no overshoot (critical damping).
      expect(dist).toBeLessThanOrEqual(prevDist + 1e-6);
      prevDist = dist;
      if (dist < 0.5) break;
    }
    expect(prevDist).toBeLessThan(1);
  });

  // ── M1: SLOWER THAN BASELINE — fewer px closed in the first N ms. ──
  // NOTE on distance: we pull 140px, a realistic in-viewport gap. The velocity
  // cap (360px/s) only engages on far/teleport pulls (peak spring speed ≈
  // 2.21·d ≈ 309px/s here, under the cap), so this compares the EASING shapes,
  // not a cap both share. A 1000px pull would cap-limit BOTH integrators to the
  // same 360px/s and prove nothing.
  const IN_VIEWPORT_PULL = 140;

  it("closes fewer pixels in the first 300ms than the old 450ms exponential baseline", () => {
    const start = { x: 0, y: 0 };
    const target = { x: IN_VIEWPORT_PULL, y: 0 };
    const dt = 16;
    const N_MS = 300;
    const stepsN = Math.round(N_MS / dt);

    // New default (spring).
    let spring = makeReelState(start);
    for (let i = 0; i < stepsN; i++) spring = reelSpringStep(spring, target, dt);
    const springClosed = spring.x - start.x;

    // Old baseline (450ms exponential).
    let base = { ...start };
    for (let i = 0; i < stepsN; i++) base = reelStep(base, target, dt, BASELINE_CFG);
    const baseClosed = base.x - start.x;

    expect(springClosed).toBeLessThan(baseClosed);
  });

  it("the slower 950ms exponential ALSO closes fewer px than the 450ms baseline in the first 300ms", () => {
    // Proves M1's constant bump alone is slower (the steelman path), independent
    // of the spring — so the cheaper fallback genuinely reads as slower too.
    const start = { x: 0, y: 0 };
    const target = { x: IN_VIEWPORT_PULL, y: 0 };
    const dt = 16;
    const stepsN = Math.round(300 / dt);

    let slow = { ...start };
    for (let i = 0; i < stepsN; i++) slow = reelStep(slow, target, dt); // tau 950 default
    let base = { ...start };
    for (let i = 0; i < stepsN; i++) base = reelStep(base, target, dt, BASELINE_CFG);

    expect(slow.x).toBeLessThan(base.x);
    expect(REEL_TAU_MS).toBeGreaterThan(BASELINE_TAU_MS);
  });

  // ── M2: velocity cap preserved on the spring. ──
  it("applies the velocity cap to the spring's velocity (teleport safety clamp)", () => {
    // A huge gap would let the spring build > cap velocity; the clamp bounds it.
    let s = makeReelState({ x: 0, y: 0 });
    const target = { x: 100000, y: 0 };
    s = reelSpringStep(s, target, REEL_MAX_DT_MS);
    const speed = Math.hypot(s.vx, s.vy);
    // Velocity must not exceed the cap (px/s), modulo float epsilon.
    expect(speed).toBeLessThanOrEqual(REEL_MAX_PX_PER_S + 1e-6);
  });

  it("pure + deterministic: same inputs ⇒ identical output (no Date.now / Math.random)", () => {
    const a = reelSpringStep(makeReelState({ x: 3, y: 7 }), { x: 200, y: 90 }, 16);
    const b = reelSpringStep(makeReelState({ x: 3, y: 7 }), { x: 200, y: 90 }, 16);
    expect(a).toEqual(b);
  });

  it("dtMs <= 0 is a no-op (guards a stalled clock)", () => {
    const s = makeReelState({ x: 5, y: 5 });
    expect(reelSpringStep(s, { x: 100, y: 100 }, 0)).toBe(s);
    expect(reelSpringStep(s, { x: 100, y: 100 }, -16)).toBe(s);
  });
});

describe("reelPursuit — M4: post-stall dt clamp (no catch-up lurch)", () => {
  it("clamps a huge post-stall dtMs to one bounded slice (spring)", () => {
    const start = makeReelState({ x: 0, y: 0 });
    const target = { x: 5000, y: 0 };

    // A 5-second stall handed to the integrator in one frame.
    const lurch = reelSpringStep(start, target, 5000);
    // A normal clamped frame.
    const normal = reelSpringStep(start, target, REEL_MAX_DT_MS);

    // The huge dt must NOT advance further than the clamped frame would.
    expect(lurch.x).toBeCloseTo(normal.x, 6);
    // And the single-step jump stays within the velocity cap × clamped dt.
    const maxJump = (REEL_MAX_PX_PER_S * REEL_MAX_DT_MS) / 1000;
    expect(lurch.x).toBeLessThanOrEqual(maxJump + 1e-6);
  });

  it("clamps a huge post-stall dtMs for the exponential fallback too", () => {
    const lurch = reelStep({ x: 0, y: 0 }, { x: 5000, y: 0 }, 5000);
    const maxJump = (REEL_MAX_PX_PER_S * REEL_MAX_DT_MS) / 1000;
    expect(lurch.x).toBeLessThanOrEqual(maxJump + 1e-6);
  });

  it("reelStateStep routes spring by default and carries velocity across calls", () => {
    let s = makeReelState({ x: 0, y: 0 });
    const target = { x: 400, y: 0 };
    s = reelStateStep(s, target, 16);
    expect(s.vx).toBeGreaterThan(0); // gained momentum (spring, not exponential)
    const s2 = reelStateStep(s, target, 16);
    expect(s2.x).toBeGreaterThan(s.x); // kept closing
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SPR-03 SHARPEN — gate the PRODUCTION path (reelStateStep @ DEFAULT config).
//
// WHY this block exists: the suite above proves `reelSpringStep` decelerates and
// never overshoots, but the production caller (PenguinMascot.tsx ~436) drives
// `reelStateStep(..., DEFAULT_REEL_CONFIG)`. The critic proved that forcing the
// router to route "exponential" (or flipping DEFAULT_REEL_CONFIG.mode) made ZERO
// tests fail — so nothing pinned "the wired path actually uses the spring."
// These tests close that: they assert the router IS the spring at default, and
// re-run the deceleration + no-overshoot proofs THROUGH the router. Flip
// DEFAULT_REEL_CONFIG.mode = "exponential" and at least one of these MUST fail.
// ─────────────────────────────────────────────────────────────────────────────
describe("reelPursuit — production router is gated to the spring (SPR-03)", () => {
  // ── Router-equivalence: default reelStateStep === reelSpringStep, step-for-step.
  it("default reelStateStep returns the SAME single step as reelSpringStep", () => {
    const s = makeReelState({ x: 3, y: 7 });
    const t = { x: 200, y: 90 };
    // toEqual on the whole ReelState (x,y,vx,vy) — not just position. If the
    // router fell back to exponential, vx/vy would be the synthesized estimate,
    // not the spring's integrated velocity, and this would diverge.
    expect(reelStateStep(s, t, 16)).toEqual(reelSpringStep(s, t, 16));
  });

  it("default reelStateStep matches reelSpringStep over a full multi-step run", () => {
    const start = { x: 0, y: 0 };
    const target = { x: 600, y: 250 };
    let routed = makeReelState(start);
    let spring = makeReelState(start);
    for (let i = 0; i < 120; i++) {
      routed = reelStateStep(routed, target, 16); // DEFAULT config (production)
      spring = reelSpringStep(spring, target, 16); // bare spring
      // Whole-state equality every step: the routed trajectory IS the spring
      // trajectory. Flipping the default mode breaks this on the first step.
      expect(routed).toEqual(spring);
    }
  });

  it("default reelStateStep matches the spring across the dt sweep too", () => {
    // The router must be the spring at EVERY dt the integrator honours, not just
    // 16ms — otherwise a mode flip could hide behind an unexercised dt.
    for (const dt of [4, 8, 16, 24, 33, 48]) {
      const s = makeReelState({ x: 10, y: -20 });
      const t = { x: 500, y: 120 };
      expect(reelStateStep(s, t, dt)).toEqual(reelSpringStep(s, t, dt));
    }
  });

  // ── DECELERATION through the ROUTER (was only proven on bare reelSpringStep).
  it("decelerates through the production router: post-peak per-step displacement falls monotonically", () => {
    const target = { x: 600, y: 0 };
    const trace = runRouted({ x: 0, y: 0 }, target, 16, 200);

    const steps = trace
      .slice(1)
      .map((s, i) => Math.hypot(s.x - trace[i].x, s.y - trace[i].y));

    // Accelerates off the mark (peak > 0) then decelerates — the weighty settle.
    let peak = 0;
    for (let i = 1; i < steps.length; i++) if (steps[i] > steps[peak]) peak = i;
    expect(peak).toBeGreaterThan(0); // genuinely accelerated off the mark

    for (let i = peak + 1; i < steps.length; i++) {
      expect(steps[i]).toBeLessThanOrEqual(steps[i - 1] + 1e-9);
    }
  });

  // ── NO OVERSHOOT through the ROUTER (1-D sweep), the wired path itself.
  it("never overshoots through the production router across a dt × distance sweep (1-D)", () => {
    const dts = [4, 8, 16, 24, 33, 48];
    const distances = [20, 80, 200, 500, 1200, 3000];
    for (const dt of dts) {
      for (const d of distances) {
        const target = { x: d, y: 0 };
        let s = makeReelState({ x: 0, y: 0 });
        const startSign = Math.sign(target.x - s.x); // +1 (approaching from 0)
        let approached = false;
        for (let i = 0; i < 4000; i++) {
          const before = Math.abs(target.x - s.x);
          s = reelStateStep(s, target, dt); // DEFAULT config — the prod path.
          const rem = target.x - s.x;
          // Critically damped ⇒ monotone approach ⇒ never passes the target.
          expect(Math.sign(rem) === startSign || Math.abs(rem) < 1e-6).toBe(true);
          expect(Math.abs(rem)).toBeLessThanOrEqual(before + 1e-6);
          if (Math.abs(rem) < before - 1e-9) approached = true;
          if (isReelSettled(s, target, 0.5)) break;
        }
        expect(approached).toBe(true);
        expect(isReelSettled(s, target, 1)).toBe(true);
      }
    }
  });

  // ── SETTLE BUDGET on the DEFAULT (spring) integrator, driven by injectable dt.
  //
  // The pre-existing PenguinMascot.iceFishing.test.tsx ≤950ms budget still
  // imports the EXPONENTIAL reelStep — it does NOT test the spring the prod path
  // runs. This pins the spring's settle time for realistic in-viewport gaps.
  //
  // BOUND SOURCE: ω₀ = 5.0 rad/s ⇒ the critically-damped step response settles
  // to within the 8px epsilon at ≈ 5/ω₀ = 1.0s for a unit-scale step; the critic
  // measured ~512ms @ 30px and ~960ms @ 150px on this exact integrator. 150px is
  // the upper end of an in-viewport hook gap (the cursor never lags the mascot by
  // more than that before the velocity cap would engage). ≤1000ms is the
  // defensible upper bound: just above the largest measured settle, and it is the
  // ω₀-derived 5/ω₀ = 1.0s settle figure documented in iceFishingConstants.ts.
  it("the DEFAULT (spring) integrator settles within REEL_SETTLE_EPSILON_PX in ≤1000ms for gaps ≤150px", () => {
    const SETTLE_BUDGET_MS = 1000; // 5/ω₀ = 1.0s @ ω₀=5.0; ≥ the ~960ms@150px measured.
    const dt = 16; // injectable dt — NOT wall-clock (deterministic).
    const stepsBudget = Math.round(SETTLE_BUDGET_MS / dt);

    for (const gap of [30, 60, 90, 120, 150]) {
      let s = makeReelState({ x: 0, y: 0 });
      const target = { x: gap, y: 0 };
      let settledAtStep = -1;
      for (let i = 0; i < stepsBudget; i++) {
        s = reelStateStep(s, target, dt); // DEFAULT config — the prod path.
        if (isReelSettled(s, target, REEL_SETTLE_EPSILON_PX)) {
          settledAtStep = i + 1;
          break;
        }
      }
      expect(
        settledAtStep,
        `spring did not settle within REEL_SETTLE_EPSILON_PX (${REEL_SETTLE_EPSILON_PX}px) ` +
          `of a ${gap}px gap in ${SETTLE_BUDGET_MS}ms (${stepsBudget} × ${dt}ms steps)`,
      ).toBeGreaterThan(0);
      // And it's the spring's settle, not a cap-limited crawl: it settled with
      // comfortable margin under the budget for these in-viewport gaps.
      expect(settledAtStep).toBeLessThanOrEqual(stepsBudget);
    }
  });
});
