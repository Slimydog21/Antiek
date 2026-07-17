/**
 * densify: instrument helpers (bait chrome + tip→bait tension + suspension +
 * productSelector + data-werner-target + reactionBus experience map) stay public
 * on the werner barrel so product shells share the fixed-station contract
 * (cursor is bait/instrument, not a chase pet).
 */
import { describe, expect, it } from "vitest";

import {
  acquireStationInstrumentSuspension,
  ambientExperienceAfterQuiet,
  baitChromeFromFollow,
  catenaryPath,
  centerLaggedTarget,
  DEFAULT_AMBIENT_QUIET_MS,
  emitWernerExperience,
  emoteDurationMs,
  emoteForExperience,
  emoteForProductDoor,
  emoteFromWernerTargetAttr,
  EMOTE_KINDS,
  FOLLOW_EASE,
  installChoreography,
  installLivingTvAmbient,
  installReactionBus,
  installTargetChoreography,
  isProductExperience,
  isStationInstrumentSuspended,
  LAG_MS,
  POINTER_IDLE_MS,
  PRODUCT_EXPERIENCES,
  productSelector,
  rodBend,
  rodBendFromPoints,
  rodLength,
  rodTipFromMascotRect,
  ROD_BUTT_LOCAL,
  ROD_HALF_BEND_DIST,
  ROD_MAX_BEND,
  ROD_TIP_LOCAL,
  SAMPLE_INTERVAL_MS,
  stationInstrumentLeaseCount,
  tipToBaitDistance,
  WERNER_EXPERIENCE_EVENT,
  WERNER_TARGET_ATTR,
} from "./index";

describe("werner instrument barrel densify", () => {
  it("exports baitChromeFromFollow for cursor-is-bait chrome", () => {
    expect(
      baitChromeFromFollow({ live: { x: 5, y: 9 }, tabHidden: false }),
    ).toEqual({ display: "block", left: "5px", top: "9px" });
  });

  it("exports tip→bait geometry shared with the fishing line densify", () => {
    const rod = { x: 0, y: 0 };
    const bait = { x: 30, y: 40 };
    expect(tipToBaitDistance(rod, bait)).toBe(50);
    expect(rodBendFromPoints(rod, bait)).toBeGreaterThan(0);
    expect(catenaryPath(rod, bait).endsWith(" 30 40")).toBe(true);
  });

  it("exports station instrument suspension for wait-arcade pointer densify", () => {
    expect(isStationInstrumentSuspended()).toBe(false);
    const release = acquireStationInstrumentSuspension("wait-arcade");
    expect(isStationInstrumentSuspended()).toBe(true);
    expect(stationInstrumentLeaseCount()).toBeGreaterThan(0);
    release();
    expect(isStationInstrumentSuspended()).toBe(false);
  });

  it("exports productSelector + emoteForProductDoor for living-TV door densify", () => {
    // Product shells stamp data-product-id; barrel densify keeps the selector
    // + emote map public so invent doors resolve without chasing a pet.
    expect(productSelector({ productId: "home-arcade", source: "click" })).toBe(
      '[data-product-id="home-arcade"]',
    );
    expect(emoteForProductDoor("home-arcade")).toBe("curious");
    expect(emoteForProductDoor("research")).toBe("thinking");
    expect(emoteForProductDoor("midnight-oil")).toBe("sleeping");
  });

  it("exports data-werner-target densify helpers for opt-in living-TV clicks", () => {
    expect(WERNER_TARGET_ATTR).toBe("data-werner-target");
    expect(emoteFromWernerTargetAttr("curious")).toBe("curious");
    expect(emoteFromWernerTargetAttr(null)).toBe("hit");
  });

  it("exports emoteForExperience densify for living-TV product reaction map", () => {
    // Host-beat inject densify: product experiences map to living-TV emotes
    // (arcade cores stay reactionBus-free; hosts inject).
    expect(emoteForExperience("highlight")).toBe("curious");
    expect(emoteForExperience("deep_research_start")).toBe("thinking");
    expect(emoteForExperience("deep_research_complete")).toBe("happy");
    expect(emoteForExperience("deep_research_error")).toBe("dizzy");
    expect(emoteForExperience("idle")).toBe("sleeping");
    expect(emoteForExperience("fail")).toBe("dizzy");
    expect(emoteForExperience("note_saved")).toBe("noted");
    expect(emoteForExperience("piece_started")).toBe("happy");
  });

  it("exports reactionBus allowlist densify (event + isProductExperience)", () => {
    // densify: host inject path stays on a closed allowlist; unknown beats ignore.
    expect(WERNER_EXPERIENCE_EVENT).toBe("antiek:werner-experience");
    expect(PRODUCT_EXPERIENCES).toContain("piece_started");
    expect(PRODUCT_EXPERIENCES.every(isProductExperience)).toBe(true);
    expect(isProductExperience("recording_started")).toBe(false);
    expect(isProductExperience("highlight")).toBe(true);
  });

  it("exports emitWernerExperience + installReactionBus densify for host inject", () => {
    // densify: hosts inject living-TV beats; arcade cores stay reactionBus-free.
    expect(typeof emitWernerExperience).toBe("function");
    expect(typeof installReactionBus).toBe("function");
    const emote = () => {};
    const teardown = installReactionBus({ emote });
    expect(typeof teardown).toBe("function");
    teardown();
  });

  it("exports living-TV ambient densify (quiet policy + installer)", () => {
    // densify: ambient episode continuity is pure policy + installLivingTvAmbient.
    expect(DEFAULT_AMBIENT_QUIET_MS).toBe(90_000);
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "deep_research_complete",
      ),
    ).toBe("note_saved");
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "idle",
      ),
    ).toBeNull();
    expect(typeof installLivingTvAmbient).toBe("function");
  });

  it("exports emote duration densify for living-TV stage beats", () => {
    // densify: every living-TV emote kind has a positive duration for stage beats.
    expect(EMOTE_KINDS.length).toBeGreaterThan(0);
    for (const kind of EMOTE_KINDS) {
      expect(emoteDurationMs(kind)).toBeGreaterThan(0);
    }
    // densify: invent door glances pin known holds (curious/thinking/sleeping).
    expect(emoteDurationMs("curious")).toBe(1200);
    expect(emoteDurationMs("thinking")).toBe(1400);
    expect(emoteDurationMs("sleeping")).toBe(2400);
  });

  it("exports mouse-follow densify for cursor-is-bait lag contract", () => {
    // densify: ice-cursor follow lags the pointer; centerLaggedTarget is pure.
    expect(LAG_MS).toBe(500);
    expect(FOLLOW_EASE).toBe(0.75);
    expect(SAMPLE_INTERVAL_MS).toBe(60);
    expect(POINTER_IDLE_MS).toBe(2000);
    expect(centerLaggedTarget({ x: 100, y: 200 }, 64)).toEqual({
      x: 68,
      y: 168,
    });
    expect(centerLaggedTarget(null, 64)).toBeNull();
  });

  it("exports choreography install densify for living-TV product + opt-in paths", () => {
    // densify: product-activate + data-werner-target installers stay public.
    expect(typeof installChoreography).toBe("function");
    expect(typeof installTargetChoreography).toBe("function");
    const stage = {
      waddleToEl: () => {},
      emote: () => {},
    } as never;
    const teardownA = installChoreography(stage, { target: null as never });
    const teardownB = installTargetChoreography(stage, {
      target: null as never,
    });
    expect(typeof teardownA).toBe("function");
    expect(typeof teardownB).toBe("function");
    teardownA();
    teardownB();
  });

  it("exports rodBend densify for instrument tension under tip→bait load", () => {
    // densify: rod flex is monotone in tip→bait distance; rest is straight.
    expect(rodBend(0)).toBe(0);
    expect(rodBend(60)).toBeCloseTo(3, 5); // half bend at half-bend distance
    expect(rodBend(100)).toBeGreaterThan(rodBend(50));
    expect(rodBend(1e9)).toBeLessThanOrEqual(6);
  });

  it("exports rodTipFromMascotRect densify for line attach at rod tip", () => {
    // densify: fishing line leaves the real rod tip in screen space (64 viewBox).
    const rect = {
      left: 100,
      top: 200,
      width: 64,
      height: 64,
      right: 164,
      bottom: 264,
      x: 100,
      y: 200,
      toJSON: () => ({}),
    } as DOMRect;
    const tip = rodTipFromMascotRect(rect, 64);
    // Default local tip is ROD_TIP_LOCAL {x:66,y:5} at scale 1.
    expect(tip).toEqual({ x: 166, y: 205 });
    const tipScaled = rodTipFromMascotRect(rect, 128);
    expect(tipScaled).toEqual({ x: 100 + 66 * 2, y: 200 + 5 * 2 });
  });

  it("exports rodLength densify for butt→tip rig contract", () => {
    // densify: rod length is fixed viewBox butt→tip (~36 units; MAX_BEND is ~1/6).
    const len = rodLength();
    expect(len).toBeCloseTo(Math.hypot(66 - 45, 5 - 34), 5);
    expect(len).toBeGreaterThan(30);
    expect(len).toBeLessThan(40);
  });

  it("exports rod bend constants densify for saturating tension curve", () => {
    // densify: HALF_BEND_DIST = 60 mid-cast; MAX_BEND = 6 asymptotic bow.
    expect(ROD_HALF_BEND_DIST).toBe(60);
    expect(ROD_MAX_BEND).toBe(6);
    expect(rodBend(ROD_HALF_BEND_DIST)).toBeCloseTo(ROD_MAX_BEND / 2, 5);
    expect(rodBend(1e9)).toBeLessThanOrEqual(ROD_MAX_BEND);
  });

  it("exports rod local anchors densify for butt→tip rig geometry", () => {
    // densify: rod tip/butt are fixed 64-viewBox locals the rig draws against.
    expect(ROD_TIP_LOCAL).toEqual({ x: 66, y: 5 });
    expect(ROD_BUTT_LOCAL).toEqual({ x: 45, y: 34 });
    expect(rodLength()).toBeCloseTo(
      Math.hypot(
        ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x,
        ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y,
      ),
      5,
    );
  });
});
