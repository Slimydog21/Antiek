import { describe, expect, it } from "vitest";

import { shouldOfferFjordSkip } from "./index";

describe("Brainstorm Fjord Skip eligibility", () => {
  it.each([
    ["while parked questions load", true, null, 0, false],
    ["when loading failed", false, "offline", 0, false],
    ["when a parked question exists", false, null, 1, false],
    ["when a question is selected", false, null, 0, true],
  ])(
    "does not offer the game %s",
    (_case, loading, error, parkedCount, hasSelection) => {
      expect(
        shouldOfferFjordSkip({ loading, error, parkedCount, hasSelection }),
      ).toBe(false);
    },
  );

  it("offers the optional game only after a successful true-empty response", () => {
    expect(
      shouldOfferFjordSkip({
        loading: false,
        error: null,
        parkedCount: 0,
        hasSelection: false,
      }),
    ).toBe(true);
  });
});
