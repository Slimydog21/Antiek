import { describe, expect, it } from "vitest";

import {
  stationAmbientClass,
  type StationAmbientInput,
} from "./stationAmbient";

const RESTING_IDLE: StationAmbientInput = {
  activeClass: null,
  idleClass: "werner-fishing",
  pointerIdle: true,
  tabHidden: false,
  dragging: false,
  directedTravel: false,
  returningHome: false,
  productEmote: false,
  reducedMotion: false,
  activityEnabled: true,
};

describe("stationAmbientClass", () => {
  it("grants one activity idle class only for visible, motion-allowed rest", () => {
    expect(stationAmbientClass(RESTING_IDLE)).toBe("werner-fishing");
  });

  it.each([
    ["missing idle class", { idleClass: null }],
    ["disabled activity", { activityEnabled: false }],
    ["reduced motion", { reducedMotion: true }],
    ["hidden tab", { tabHidden: true }],
    ["drag", { dragging: true }],
    ["directed travel", { directedTravel: true }],
    ["return home", { returningHome: true }],
    ["product emote", { productEmote: true }],
  ] satisfies Array<[string, Partial<StationAmbientInput>]>) (
    "withholds ambient during %s",
    (_label, override) => {
      expect(stationAmbientClass({ ...RESTING_IDLE, ...override })).toBeNull();
    },
  );

  it("selects the activity-owned active class without inventing one", () => {
    expect(
      stationAmbientClass({
        ...RESTING_IDLE,
        pointerIdle: false,
        activeClass: "activity-active",
      }),
    ).toBe("activity-active");
    expect(
      stationAmbientClass({ ...RESTING_IDLE, pointerIdle: false }),
    ).toBeNull();
  });

  it("does not mutate or normalize an activity-owned class", () => {
    const input = { ...RESTING_IDLE, idleClass: "activity-own-ambient" };
    expect(stationAmbientClass(input)).toBe("activity-own-ambient");
    expect(input).toEqual({ ...RESTING_IDLE, idleClass: "activity-own-ambient" });
  });
});
