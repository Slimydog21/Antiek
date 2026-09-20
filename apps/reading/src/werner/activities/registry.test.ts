import { describe, expect, it } from "vitest";

import {
  getActivity,
  getDefaultActivity,
  listActivities,
  restActivity,
  researchLensActivity,
  registerActivity,
  speakingResonanceActivity,
  writingNibActivity,
} from "./index";

/**
 * Registry unit tests — pinned against the REAL rest activity (the calm
 * default). Importing "./index" self-registers rest as the default, so these
 * assertions run against the production catalog.
 */
describe("station activity registry", () => {
  it("getActivity('rest') returns the calm activity", () => {
    expect(getActivity("rest")).toBe(restActivity);
  });

  it("listActivities() includes rest and is frozen", () => {
    const all = listActivities();
    expect(all).toContain(restActivity);
    expect(Object.isFrozen(all)).toBe(true);
  });

  it("rest is the default activity", () => {
    expect(getDefaultActivity()).toBe(restActivity);
  });

  it("registers research-lens without replacing the default", () => {
    expect(getActivity("research-lens")).toBe(researchLensActivity);
    expect(listActivities()).toEqual([
      restActivity,
      researchLensActivity,
      writingNibActivity,
      speakingResonanceActivity,
    ]);
    expect(getDefaultActivity()).toBe(restActivity);
  });

  it("registerActivity is idempotent for the same object", () => {
    const before = listActivities().filter(
      (a) => a.id === "rest",
    ).length;
    // Re-register the SAME id — the catalog must not grow a duplicate entry.
    registerActivity(restActivity, { default: true });
    const after = listActivities().filter((a) => a.id === "rest").length;
    expect(before).toBe(1);
    expect(after).toBe(1);
    expect(getActivity("rest")).toBe(restActivity);
  });

  it("rejects a conflicting replacement for an existing id", () => {
    const conflicting = {
      ...restActivity,
      label: "Impostor rest",
    };
    expect(() => registerActivity(conflicting)).toThrow(
      'Werner station: activity "rest" is already registered',
    );
    expect(getActivity("rest")).toBe(restActivity);
  });

  describe("rest activity shape", () => {
    it("ambient: no idle or active classes — the calm station", () => {
      expect(restActivity.ambient.idleClass).toBeNull();
      expect(restActivity.ambient.activeClass).toBeNull();
    });

    it("unlock kind is 'default'", () => {
      expect(restActivity.unlock).toEqual({ kind: "default" });
    });

    it("instrument renders nothing (no cursor instrument — operator directive)", () => {
      expect(restActivity.instrument.render).toBeNull();
      expect(restActivity.instrument.reads).toEqual([]);
    });
  });

  describe("research-lens activity shape", () => {
    it("declares the route policy and no idle mascot ambient", () => {
      expect(researchLensActivity.unlock).toEqual({
        kind: "route",
        policyId: "knowledge-work",
      });
      expect(researchLensActivity.ambient).toEqual({
        activeClass: null,
        idleClass: null,
      });
    });

    it("reads only the cursor seam", () => {
      expect(researchLensActivity.instrument.reads).toEqual([
        "live",
        "pointerIdle",
        "tabHidden",
      ]);
    });
  });

  describe("writing-nib activity shape", () => {
    it("declares the writing route policy and no mascot ambient", () => {
      expect(writingNibActivity.unlock).toEqual({
        kind: "route",
        policyId: "writing-work",
      });
      expect(writingNibActivity.ambient).toEqual({
        activeClass: null,
        idleClass: null,
      });
    });

    it("reads only the cursor seam", () => {
      expect(writingNibActivity.instrument.reads).toEqual([
        "live",
        "pointerIdle",
        "tabHidden",
      ]);
    });
  });

  describe("speaking-resonance activity shape", () => {
    it("declares the speaking route policy and no mascot ambient", () => {
      expect(speakingResonanceActivity.unlock).toEqual({
        kind: "route",
        policyId: "speaking-work",
      });
      expect(speakingResonanceActivity.ambient).toEqual({
        activeClass: null,
        idleClass: null,
      });
    });

    it("reads only the cursor seam", () => {
      expect(speakingResonanceActivity.instrument.reads).toEqual([
        "live",
        "pointerIdle",
        "tabHidden",
      ]);
    });
  });
});
