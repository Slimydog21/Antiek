/**
 * wernerState.test.ts — the steering state machine (SPR-05).
 *
 * Pure reducer, so every claim is a direct (state, event) → state assertion
 * with no renderer. Load-bearing transitions:
 *  - directed actions (waddle/emote) supersede each other (latest-wins) and
 *    carry the ambient state to RESUME into;
 *  - an emote fired mid-follow resumes following, not a hard idle;
 *  - `frozen` is a hard floor — every command is a no-op except `unfreeze`;
 *  - stale late events (arrived/emoteDone after the action was superseded)
 *    are ignored, never crash.
 */
import { describe, expect, it } from "vitest";

import {
  FISHING_BEATS,
  FISHING_CYCLE_MS,
  fishingStep,
  INITIAL_WERNER_STATE,
  isBusy,
  shouldFish,
  wernerReducer,
  type FishingBeat,
  type WernerState,
} from "./wernerState";

const idle: WernerState = { name: "idle", resume: "idle" };

describe("wernerReducer", () => {
  it("starts idle, resuming idle", () => {
    expect(INITIAL_WERNER_STATE).toEqual(idle);
  });

  it("follow on → following; off → idle (ambient floor moves)", () => {
    const following = wernerReducer(idle, { type: "follow", on: true });
    expect(following).toEqual({ name: "following", resume: "following" });
    const back = wernerReducer(following, { type: "follow", on: false });
    expect(back).toEqual({ name: "idle", resume: "idle" });
  });

  it("waddle from following resumes following on arrival (mouse-follow not silently cancelled)", () => {
    const following: WernerState = { name: "following", resume: "following" };
    const waddling = wernerReducer(following, { type: "waddle" });
    expect(waddling).toEqual({ name: "waddling", resume: "following" });
    const arrived = wernerReducer(waddling, { type: "arrived" });
    expect(arrived).toEqual({ name: "following", resume: "following" });
  });

  it("emote from idle resumes idle when the beat ends", () => {
    const emoting = wernerReducer(idle, { type: "emote" });
    expect(emoting).toEqual({ name: "emoting", resume: "idle" });
    expect(wernerReducer(emoting, { type: "emoteDone" })).toEqual(idle);
  });

  it("emote mid-follow resumes following (carries the ambient)", () => {
    const following: WernerState = { name: "following", resume: "following" };
    const emoting = wernerReducer(following, { type: "emote" });
    expect(emoting.resume).toBe("following");
    expect(wernerReducer(emoting, { type: "emoteDone" })).toEqual({
      name: "following",
      resume: "following",
    });
  });

  it("latest-wins: a new waddle supersedes an in-flight emote, keeping the ambient", () => {
    const following: WernerState = { name: "following", resume: "following" };
    const emoting = wernerReducer(following, { type: "emote" });
    const waddling = wernerReducer(emoting, { type: "waddle" });
    expect(waddling).toEqual({ name: "waddling", resume: "following" });
  });

  it("follow toggled DURING a directed action only updates the resume, not the state", () => {
    const waddling: WernerState = { name: "waddling", resume: "idle" };
    const next = wernerReducer(waddling, { type: "follow", on: true });
    expect(next).toEqual({ name: "waddling", resume: "following" });
  });

  it("stale arrived/emoteDone after supersession are ignored (no crash, no flip)", () => {
    const waddling: WernerState = { name: "waddling", resume: "idle" };
    // emoteDone doesn't belong to a waddle → ignored.
    expect(wernerReducer(waddling, { type: "emoteDone" })).toBe(waddling);
    const emoting: WernerState = { name: "emoting", resume: "idle" };
    // arrived doesn't belong to an emote → ignored.
    expect(wernerReducer(emoting, { type: "arrived" })).toBe(emoting);
  });

  it("freeze is a hard floor: every command is a no-op except unfreeze", () => {
    const frozen = wernerReducer(idle, { type: "freeze" });
    expect(frozen).toEqual({ name: "frozen", resume: "idle" });
    for (const event of [
      { type: "waddle" } as const,
      { type: "emote" } as const,
      { type: "follow", on: true } as const,
      { type: "arrived" } as const,
      { type: "emoteDone" } as const,
      { type: "idle" } as const,
    ]) {
      expect(wernerReducer(frozen, event)).toBe(frozen);
    }
    expect(wernerReducer(frozen, { type: "unfreeze" })).toEqual(INITIAL_WERNER_STATE);
  });

  it("idle is a hard return to rest from any non-frozen state", () => {
    const emoting: WernerState = { name: "emoting", resume: "following" };
    expect(wernerReducer(emoting, { type: "idle" })).toEqual(idle);
  });

  it("isBusy reflects directed actions only", () => {
    expect(isBusy(idle)).toBe(false);
    expect(isBusy({ name: "following", resume: "following" })).toBe(false);
    expect(isBusy({ name: "waddling", resume: "idle" })).toBe(true);
    expect(isBusy({ name: "emoting", resume: "idle" })).toBe(true);
    expect(isBusy({ name: "frozen", resume: "idle" })).toBe(false);
  });
});

/**
 * SPR-05 — the endless fishing loop (the Scrat / Tom-&-Jerry cycle).
 *
 * Two concerns, two suites:
 *  - the GATE (shouldFish): the loop OWNS Werner only at ambient rest + pointer
 *    idle; a pointer move OR any directed/following/frozen state hands him back
 *    (the loop XOR the reel — one owner at a time);
 *  - the CYCLE (FISHING_BEATS + fishingStep): the comic beat order, that it
 *    LOOPS, and that it NEVER reaches a "caught" terminal (the gag's whole soul).
 */
describe("fishing loop — the gate (shouldFish)", () => {
  const following: WernerState = { name: "following", resume: "following" };
  const waddling: WernerState = { name: "waddling", resume: "idle" };
  const emoting: WernerState = { name: "emoting", resume: "idle" };
  const frozen: WernerState = { name: "frozen", resume: "idle" };

  it("idle + pointer idle → the loop owns Werner", () => {
    expect(shouldFish(idle, true)).toBe(true);
  });

  it("idle + pointer MOVED → loop stands down (reel takes over)", () => {
    // This is the load-bearing gate. If the pointer-idle term were removed from
    // shouldFish, this would flip to true and the loop would fight the reel.
    expect(shouldFish(idle, false)).toBe(false);
  });

  it("following → never fishes, even with the pointer idle (the reel owns him)", () => {
    expect(shouldFish(following, true)).toBe(false);
    expect(shouldFish(following, false)).toBe(false);
  });

  it("waddling / emoting → never fishes (a directed action owns the position)", () => {
    expect(shouldFish(waddling, true)).toBe(false);
    expect(shouldFish(emoting, true)).toBe(false);
  });

  it("frozen → never fishes (reduced motion / hidden tab: no involuntary gag)", () => {
    expect(shouldFish(frozen, true)).toBe(false);
    expect(shouldFish(frozen, false)).toBe(false);
  });

  it("clean hand-off BOTH directions: idle⇄follow flips ownership with the same predicate", () => {
    // active → idle: a pointer move while following keeps the reel; going idle
    // (pointer still) starts the loop.
    expect(shouldFish(following, false)).toBe(false); // reel
    // The shell flips the ambient state to idle when follow turns off; THEN a
    // still pointer starts the loop.
    const wentIdle = wernerReducer(following, { type: "follow", on: false });
    expect(wentIdle).toEqual(idle);
    expect(shouldFish(wentIdle, true)).toBe(true); // loop
    // idle → active: the pointer moves; pointerIdle flips false → loop drops.
    expect(shouldFish(wentIdle, false)).toBe(false);
  });
});

describe("fishing loop — the cycle (FISHING_BEATS + fishingStep)", () => {
  const ORDER: FishingBeat[] = [
    "cast",
    "wait",
    "bob",
    "nibble",
    "yank",
    "miss",
    "slump",
    "reset",
  ];

  it("the beat table is the comic cycle in order, with a commented holdMs each", () => {
    expect(FISHING_BEATS.map((s) => s.beat)).toEqual(ORDER);
    for (const step of FISHING_BEATS) {
      expect(step.holdMs).toBeGreaterThan(0);
      expect(step.intent.length).toBeGreaterThan(0);
    }
  });

  it("the cartoon NEVER reaches a 'caught' terminal — there is no such beat", () => {
    // The gag's soul: he never lands the fish. Structural guarantee — no beat is
    // named caught/catch/landed/success, and every beat is one of the known set.
    for (const step of FISHING_BEATS) {
      expect(["caught", "catch", "landed", "success"]).not.toContain(step.beat);
    }
  });

  it("comic timing: the held wait is the longest beat; yank is the snappiest", () => {
    const by = Object.fromEntries(FISHING_BEATS.map((s) => [s.beat, s.holdMs]));
    // Tom-&-Jerry: a long held wait, a fast snap yank, a long disappointed slump.
    expect(by.wait).toBe(Math.max(...FISHING_BEATS.map((s) => s.holdMs)));
    expect(by.yank).toBe(Math.min(...FISHING_BEATS.map((s) => s.holdMs)));
    expect(by.wait).toBeGreaterThan(by.yank); // held beat >> snap
    expect(by.slump).toBeGreaterThan(by.miss); // settle drawn out past the miss
  });

  it("a deterministic clock walk steps cast→…→reset in order across one cycle", () => {
    // Sample the MIDPOINT of each beat (no Date.now, no timers — pure elapsed
    // ms). The midpoints land squarely inside each beat regardless of rounding.
    let acc = 0;
    const seen: FishingBeat[] = [];
    for (const step of FISHING_BEATS) {
      const mid = acc + step.holdMs / 2;
      seen.push(fishingStep(mid).beat);
      acc += step.holdMs;
    }
    expect(seen).toEqual(ORDER);
  });

  it("the cycle LOOPS: one full period later, the same elapsed phase repeats", () => {
    // At t and t + CYCLE the beat is identical → the loop is endless, no terminal.
    for (let t = 0; t < FISHING_CYCLE_MS; t += 137) {
      expect(fishingStep(t + FISHING_CYCLE_MS).beat).toBe(fishingStep(t).beat);
    }
  });

  it("after the slump+reset it loops back to cast (never a payoff)", () => {
    // The very start of the cycle is cast; the very end (reset) is followed by
    // cast on the next loop, not by any "caught" state.
    expect(fishingStep(0).beat).toBe("cast");
    expect(fishingStep(FISHING_CYCLE_MS).beat).toBe("cast"); // wrapped
    expect(fishingStep(FISHING_CYCLE_MS - 1).beat).toBe("reset"); // last beat
    expect(fishingStep(FISHING_CYCLE_MS + 1).beat).toBe("cast"); // looped
  });

  it("the near-catch + miss BEATS are present and adjacent (the gag lands every cycle)", () => {
    // It must not skip wait → slump: nibble (hope) → yank → miss must appear,
    // in that order, between wait and slump.
    const order = FISHING_BEATS.map((s) => s.beat);
    expect(order.indexOf("nibble")).toBeLessThan(order.indexOf("yank"));
    expect(order.indexOf("yank")).toBeLessThan(order.indexOf("miss"));
    expect(order.indexOf("wait")).toBeLessThan(order.indexOf("nibble"));
    expect(order.indexOf("miss")).toBeLessThan(order.indexOf("slump"));
  });

  it("beatPhase runs 0..1 within a beat and is clamped on a stray pre-mount tick", () => {
    const cast = FISHING_BEATS[0];
    expect(fishingStep(0).beatPhase).toBe(0);
    expect(fishingStep(cast.holdMs / 2).beatPhase).toBeCloseTo(0.5, 5);
    // Negative / NaN guard → clamped to the cast at phase 0 (no NaN render).
    expect(fishingStep(-100)).toEqual({ beat: "cast", index: 0, beatPhase: 0 });
    expect(fishingStep(NaN)).toEqual({ beat: "cast", index: 0, beatPhase: 0 });
  });
});
