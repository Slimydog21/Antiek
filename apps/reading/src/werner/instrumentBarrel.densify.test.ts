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
  installLivingTvAmbient,
  installReactionBus,
  isProductExperience,
  isStationInstrumentSuspended,
  LAG_MS,
  PRODUCT_EXPERIENCES,
  productSelector,
  rodBendFromPoints,
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
    expect(centerLaggedTarget({ x: 100, y: 200 }, 64)).toEqual({
      x: 68,
      y: 168,
    });
    expect(centerLaggedTarget(null, 64)).toBeNull();
  });
});
