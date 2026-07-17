/**
 * densify: instrument helpers (bait chrome + tip→bait tension + suspension +
 * productSelector + data-werner-target) stay public on the werner barrel so
 * product shells share the fixed-station contract (cursor is bait/instrument,
 * not a chase pet).
 */
import { describe, expect, it } from "vitest";

import {
  acquireStationInstrumentSuspension,
  baitChromeFromFollow,
  catenaryPath,
  emoteForProductDoor,
  emoteFromWernerTargetAttr,
  isStationInstrumentSuspended,
  productSelector,
  rodBendFromPoints,
  stationInstrumentLeaseCount,
  tipToBaitDistance,
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
});
