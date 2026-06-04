/**
 * gateHonesty.contract.test.tsx — the read-only gate discipline, mechanically.
 *
 * This is the enforcement of the gate-honesty contract written in
 * docs/decisions/speak-private-public-spine.md (SPR-01 M5). It pins two
 * invariants on the shared vocabulary module (lib/speakVocab.ts) so that
 * SPR-03 (PublicLane + gate state) and SPR-04 (payout legibility) cannot
 * accidentally break them when they add or reword copy:
 *
 *   1. No GATE phrase grants the user false agency. Gates are read-only
 *      operator actions (a post-counsel env flip), so no gate sentence may use
 *      a user-actionable verb — "enable / unlock / activate / close the gate".
 *      The phrasing must describe a FUTURE state, never an affordance.
 *   2. No rendered string leaks a raw env-flag name. The flag names
 *      (ANTIEK_SPEAK_PUBLIC_PUBLISHING / ANTIEK_SPEAK_PUBLIC_ECOSYSTEM /
 *      ANTIEK_STRIPE_PROVIDER) belong to the substrate seam, never to a user.
 *
 * It is a PURE-MODULE test: it imports speakVocab and asserts on its exported
 * strings. It does NOT render the lane components — the contract lives in the
 * vocab module, so that is exactly what it scans.
 */
import { describe, expect, it } from "vitest";

import {
  GATE_PHRASES,
  LANE_LABELS,
  AGREEMENT_WORDS,
  gatePhraseStrings,
  allRenderedPhrases,
} from "../../../lib/speakVocab";

// A verb that, in a gate sentence, would imply the USER can act on the gate.
// "close the gate" is matched as a phrase; the rest as standalone verbs.
const USER_ACTION = /enable|unlock|activate|close the gate/i;

// The substrate env flags — none may appear in anything we render.
const FLAG_NAMES = [
  "ANTIEK_SPEAK_PUBLIC_ECOSYSTEM",
  "ANTIEK_SPEAK_PUBLIC_PUBLISHING",
  "ANTIEK_STRIPE_PROVIDER",
];

describe("speakVocab — gate-honesty contract", () => {
  it("exposes gate phrases to scan", () => {
    // Guard against a future refactor silently emptying the surface and making
    // the discipline checks vacuously pass.
    expect(gatePhraseStrings().length).toBeGreaterThan(0);
    expect(allRenderedPhrases().length).toBeGreaterThan(0);
  });

  it("no gate phrase grants the user false agency (no enable/unlock/activate/close the gate)", () => {
    for (const phrase of gatePhraseStrings()) {
      expect(
        USER_ACTION.test(phrase),
        `gate phrase implies a user can act on the gate: "${phrase}"`,
      ).toBe(false);
    }
  });

  it("gate phrasing is future-tense, not an affordance (sanity on the canonical sentence)", () => {
    // The exemplar the spec names: describes a future state, offers no action.
    expect(GATE_PHRASES.publicSharing.whenGated).toMatch(/opens after/i);
  });

  it("no rendered string leaks a raw env-flag name", () => {
    for (const phrase of allRenderedPhrases()) {
      for (const flag of FLAG_NAMES) {
        expect(
          phrase.includes(flag),
          `rendered string leaks the env-flag "${flag}": "${phrase}"`,
        ).toBe(false);
      }
    }
  });

  it("the agreement words never say 'proven' or 'true'", () => {
    for (const word of Object.values(AGREEMENT_WORDS)) {
      expect(/\b(proven|true)\b/i.test(word)).toBe(false);
    }
  });

  it("lane labels are the canonical two", () => {
    expect(LANE_LABELS.yours).toBe("People you're remembering");
    expect(LANE_LABELS.public).toBe("Public remembrances");
  });
});
