import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AdSlot, { type AdItem } from "./AdSlot";

const baseAd: AdItem = {
  campaign_id: "camp-1",
  advertiser_name: "Measured SaaS",
  creative_headline: "Ship better research workflows",
  creative_url: "https://example.com/?ref=antiek",
  sector: "saas",
  intent: "research",
};

afterEach(() => cleanup());

describe("AdSlot", () => {
  it.each(["javascript:alert(1)", "data:text/html,owned", "/relative/path", " "])(
    "does not render unsafe campaign URLs as clickable external links: %s",
    (creativeUrl) => {
      render(<AdSlot ad={{ ...baseAd, creative_url: creativeUrl }} />);

      expect(
        screen.getByRole("link", { name: "Ship better research workflows" }).getAttribute("href"),
      ).toBe("#");
    },
  );

  it("trims and preserves absolute http campaign URLs", () => {
    render(<AdSlot ad={{ ...baseAd, creative_url: " https://example.com/path " }} />);

    expect(
      screen.getByRole("link", { name: "Ship better research workflows" }).getAttribute("href"),
    ).toBe("https://example.com/path");
  });
});
