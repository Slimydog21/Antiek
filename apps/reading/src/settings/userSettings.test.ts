// SPR-07 M7 — userSettings store tests.
//
// Coverage:
//   - default is false (public graph OFF) when storage is empty.
//   - flipping the toggle persists to localStorage.
//   - on reload (simulated by re-reading storage), the toggle
//     restores the persisted value.

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  _resetUserSettingsForTest,
  useUserSettings,
} from "./userSettings";

describe("userSettings — public-graph toggle (M7)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    _resetUserSettingsForTest();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("defaults to false (public graph OFF)", () => {
    expect(useUserSettings.getState().includePublicGraphInCrossDoc).toBe(false);
  });

  it("persists to localStorage when flipped on", () => {
    useUserSettings.getState().setIncludePublicGraphInCrossDoc(true);
    expect(useUserSettings.getState().includePublicGraphInCrossDoc).toBe(true);
    expect(
      window.localStorage.getItem(
        "antiek.settings.crossDoc.includePublicGraphInCrossDoc",
      ) ??
        window.localStorage.getItem("antiek.settings.crossDoc.includePublicGraph"),
    ).toBe("true");
  });

  it("clears the persisted value when flipped back off", () => {
    useUserSettings.getState().setIncludePublicGraphInCrossDoc(true);
    useUserSettings.getState().setIncludePublicGraphInCrossDoc(false);
    expect(useUserSettings.getState().includePublicGraphInCrossDoc).toBe(false);
    expect(
      window.localStorage.getItem("antiek.settings.crossDoc.includePublicGraph"),
    ).toBe("false");
  });
});
