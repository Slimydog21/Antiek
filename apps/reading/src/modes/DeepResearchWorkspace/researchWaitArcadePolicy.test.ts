import { describe, expect, it } from "vitest";

import {
  deriveResearchWaitArcadeMode,
  type ResearchWaitArcadePolicyInput,
} from "./researchWaitArcadePolicy";

const ELIGIBLE: ResearchWaitArcadePolicyInput = {
  featureEnabled: true,
  hasAuthoritativeSnapshot: true,
  researchCount: 3,
  allTerminal: false,
  reducedMotion: false,
  offerReady: false,
  optedIn: false,
};

describe("deriveResearchWaitArcadeMode", () => {
  it.each([
    ["disabled", { featureEnabled: false }],
    ["unobserved", { hasAuthoritativeSnapshot: false }],
    ["empty", { researchCount: 0 }],
    ["terminal", { allTerminal: true }],
    ["reduced motion", { reducedMotion: true }],
  ])("hides for %s sessions", (_name, patch) => {
    expect(deriveResearchWaitArcadeMode({ ...ELIGIBLE, ...patch })).toBe(
      "hidden",
    );
  });

  it("waits, offers, then plays only after explicit opt-in", () => {
    expect(deriveResearchWaitArcadeMode(ELIGIBLE)).toBe("waiting");
    expect(
      deriveResearchWaitArcadeMode({ ...ELIGIBLE, offerReady: true }),
    ).toBe("offer");
    expect(
      deriveResearchWaitArcadeMode({
        ...ELIGIBLE,
        offerReady: true,
        optedIn: true,
      }),
    ).toBe("playing");
  });

  it("terminal authority wins over a playing arcade", () => {
    expect(
      deriveResearchWaitArcadeMode({
        ...ELIGIBLE,
        offerReady: true,
        optedIn: true,
        allTerminal: true,
      }),
    ).toBe("hidden");
  });

  it("opted-in densify plays even before offerReady (explicit opt-in owns mode)", () => {
    // densify: once the operator opts in, wait arcade is playing without
    // requiring the offer clock — terminal/hidden gates still win above.
    expect(
      deriveResearchWaitArcadeMode({
        ...ELIGIBLE,
        offerReady: false,
        optedIn: true,
      }),
    ).toBe("playing");
  });
});
