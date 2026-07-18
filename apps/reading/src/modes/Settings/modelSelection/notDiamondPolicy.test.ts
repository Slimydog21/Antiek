import { describe, expect, it } from "vitest";

import {
  defaultNotDiamondState,
  isLiveRouteForbidden,
  setNotDiamondMode,
} from "./notDiamondPolicy";

describe("notDiamondPolicy", () => {
  it("defaults to disabled with no live adapter", () => {
    const s = defaultNotDiamondState();
    expect(s.mode).toBe("disabled");
    expect(s.liveAdapterEnabled).toBe(false);
    expect(s.authority).toBe("advisory_or_less");
  });

  it("never enables live adapter when mode changes", () => {
    let s = defaultNotDiamondState();
    s = setNotDiamondMode(s, "shadow");
    expect(s.mode).toBe("shadow");
    expect(s.liveAdapterEnabled).toBe(false);
    s = setNotDiamondMode(s, "advisory");
    expect(s.liveAdapterEnabled).toBe(false);
  });

  it("forbids live route authority for every mode", () => {
    expect(isLiveRouteForbidden("disabled")).toBe(true);
    expect(isLiveRouteForbidden("shadow")).toBe(true);
    expect(isLiveRouteForbidden("advisory")).toBe(true);
  });
});
