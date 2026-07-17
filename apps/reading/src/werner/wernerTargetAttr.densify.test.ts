/**
 * densify: data-werner-target opt-in contract (SPR-10 M4) — pure attr→emote
 * mapping + attribute name so invent product surfaces (Home / ArcadeCabinet)
 * stamp the same living-TV target path installTargetChoreography resolves.
 */
import { describe, expect, it } from "vitest";

import {
  WERNER_TARGET_ATTR,
  emoteFromWernerTargetAttr,
} from "./choreography";
import { EMOTE_KINDS } from "./emotes";

describe("data-werner-target densify", () => {
  it("pins the opt-in attribute contract", () => {
    expect(WERNER_TARGET_ATTR).toBe("data-werner-target");
  });

  it("maps named living-TV emote values; bare/unknown fall back to hit densify", () => {
    for (const kind of EMOTE_KINDS) {
      expect(emoteFromWernerTargetAttr(kind)).toBe(kind);
    }
    expect(emoteFromWernerTargetAttr("")).toBe("hit");
    expect(emoteFromWernerTargetAttr(null)).toBe("hit");
    expect(emoteFromWernerTargetAttr("not-an-emote")).toBe("hit");
  });

  it("matches invent surface stamping densify (curious product doors)", () => {
    // Home workflow chips + home-arcade CTA + ArcadeCabinet stamp "curious".
    expect(emoteFromWernerTargetAttr("curious")).toBe("curious");
  });
});
