/**
 * Manual sponsor fill — house fallback + static creative (website ads MVP).
 * No network; mirrors BiddingPolicy.MANUAL_SPONSOR only as a fill label.
 */
import { describe, expect, it } from "vitest";

import {
  BIDDING_POLICY_MANUAL_SPONSOR,
  readManualSponsorCreativeFromEnv,
  resolveManualSponsorFill,
} from "./manualSponsorFill";

describe("manualSponsorFill", () => {
  it("exposes the substrate BiddingPolicy.MANUAL_SPONSOR wire value", () => {
    expect(BIDDING_POLICY_MANUAL_SPONSOR).toBe("manual_sponsor");
  });

  it("falls back to house when env creative is incomplete", () => {
    const env = {
      VITE_MANUAL_SPONSOR_NAME: "Acme",
      // landing missing → incomplete
    } as ImportMetaEnv;
    expect(readManualSponsorCreativeFromEnv(env)).toBeNull();
    expect(resolveManualSponsorFill(null)).toEqual({
      kind: "house",
      house: null,
    });
  });

  it("builds an ad fill from a complete static creative", () => {
    const creative = {
      advertiserName: "Acme Labs",
      creativeUrl: "/mark-32.png",
      landingUrl: "https://example.com/sponsor",
    };
    expect(resolveManualSponsorFill(creative)).toEqual({
      kind: "ad",
      ad: creative,
    });
  });

  it("defaults creativeUrl to /mark-32.png when only name+landing are set", () => {
    const env = {
      VITE_MANUAL_SPONSOR_NAME: "Acme Labs",
      VITE_MANUAL_SPONSOR_LANDING_URL: "https://example.com",
    } as ImportMetaEnv;
    expect(readManualSponsorCreativeFromEnv(env)).toEqual({
      advertiserName: "Acme Labs",
      creativeUrl: "/mark-32.png",
      landingUrl: "https://example.com",
    });
  });
});
