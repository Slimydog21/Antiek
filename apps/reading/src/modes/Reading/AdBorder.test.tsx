import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AdBorder, { type AdFillView, normalizeAdFill } from "./AdBorder";

afterEach(() => cleanup());

const paidFill: AdFillView = {
  kind: "ad",
  ad: {
    advertiserName: " Measured SaaS ",
    creativeUrl: " https://example.com/creative.png ",
    landingUrl: " https://example.com/?ref=antiek ",
  },
};

describe("Reading AdBorder", () => {
  it("trims and preserves absolute http paid ad URLs", () => {
    const { container } = render(<AdBorder slotId="slot-1" position="top" fill={paidFill} />);

    const link = screen.getByRole("link", { name: /Measured SaaS/ });
    expect(link.getAttribute("href")).toBe("https://example.com/?ref=antiek");
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "https://example.com/creative.png",
    );
  });

  it.each([
    { creativeUrl: "javascript:alert(1)", landingUrl: "https://example.com/" },
    { creativeUrl: "https://example.com/creative.png", landingUrl: "data:text/html,owned" },
    { creativeUrl: "/relative/creative.png", landingUrl: "https://example.com/" },
    { creativeUrl: "https://example.com/creative.png", landingUrl: "/relative/landing" },
    {
      creativeUrl: "https://example.com/creative.png",
      landingUrl: "https://example.com/",
      advertiserName: " ",
    },
  ])("degrades unsafe paid ad fill to house %#", (ad) => {
    render(
      <AdBorder
        slotId="slot-unsafe"
        position="top"
        fill={{
          kind: "ad",
          ad: {
            advertiserName: ad.advertiserName ?? "Unsafe Advertiser",
            creativeUrl: ad.creativeUrl,
            landingUrl: ad.landingUrl,
          },
        }}
      />,
    );

    expect(screen.getByLabelText("Recommended reading")).toBeTruthy();
    expect(screen.getByText("From the library")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Unsafe Advertiser/ })).toBeNull();
  });

  it("uses a supplied house promo when an unsafe paid fill degrades", () => {
    const safeFill = normalizeAdFill({
      kind: "ad",
      ad: {
        advertiserName: "Unsafe Advertiser",
        creativeUrl: "javascript:alert(1)",
        landingUrl: "https://example.com/",
      },
      house: { documentId: "doc-2", title: "Safe next read", author: "Curator" },
    });

    expect(safeFill).toEqual({
      kind: "house",
      house: { documentId: "doc-2", title: "Safe next read", author: "Curator" },
    });
  });
});
