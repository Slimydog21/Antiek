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
  INITIAL_WERNER_STATE,
  isBusy,
  wernerReducer,
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
