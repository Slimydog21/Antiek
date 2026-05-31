/**
 * WindowAdBorder.test.tsx — SPR-09 M3 acceptance.
 *
 * The Times-Square frame reuses the Read-mode AdBorder primitive, so the
 * never-blank house fallback + suppression contract is inherited. These tests
 * assert the SPR-09 additions on top:
 *   - parent-supplied per-edge fills render (and missing edges → house, never blank);
 *   - a paid ad fires onImpression once;
 *   - a suppressed paid-ad edge degrades to house + fires onSuppressed (no ad);
 *   - reduced-motion is honored by construction (data-reduced-motion stamp).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { WindowAdBorder } from "./WindowAdBorder";
import type { AdFillView } from "../../modes/Reading/AdBorder";

function stubMatchMedia(reduce: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: reduce && query.includes("reduce"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

const PAID: AdFillView = {
  kind: "ad",
  ad: {
    advertiserName: "A Relevant Advertiser",
    creativeUrl: "https://placehold.co/64",
    landingUrl: "https://example.com",
  },
};

beforeEach(() => stubMatchMedia(false));
afterEach(cleanup);

describe("WindowAdBorder", () => {
  it("renders four edges; missing edges fall back to a house slot (never blank)", () => {
    render(<WindowAdBorder windowId="w1" />);
    // No fills supplied → every edge is a house slot. The neutral house card
    // says "From the library", never an empty rail.
    const houseCards = screen.getAllByText("From the library");
    expect(houseCards.length).toBeGreaterThanOrEqual(2); // top + bottom always
    // Recommended-reading label is present on house edges (never "blank").
    expect(screen.getAllByLabelText("Recommended reading").length).toBeGreaterThanOrEqual(2);
  });

  it("renders a paid ad and fires onImpression once for it", () => {
    const onImpression = vi.fn();
    render(
      <WindowAdBorder windowId="w2" fills={{ top: PAID }} onImpression={onImpression} />,
    );
    expect(screen.getByText("A Relevant Advertiser")).toBeTruthy();
    expect(onImpression).toHaveBeenCalledTimes(1);
    expect(onImpression).toHaveBeenCalledWith("win:w2:top", "A Relevant Advertiser");
  });

  it("suppresses a paid-ad edge: degrades to house, fires onSuppressed, no ad", () => {
    const onImpression = vi.fn();
    const onSuppressed = vi.fn();
    render(
      <WindowAdBorder
        windowId="w3"
        fills={{ top: PAID }}
        suppressed={{ top: true }}
        onImpression={onImpression}
        onSuppressed={onSuppressed}
      />,
    );
    // The paid creative must NOT render on a suppressed edge.
    expect(screen.queryByText("A Relevant Advertiser")).toBeNull();
    // It degraded to a house slot (never blank).
    expect(screen.getAllByText("From the library").length).toBeGreaterThanOrEqual(1);
    // Suppression reported; impression NOT fired for the suppressed edge.
    expect(onSuppressed).toHaveBeenCalledTimes(1);
    expect(onSuppressed.mock.calls[0][0]).toBe("win:w3:top");
    expect(onImpression).not.toHaveBeenCalled();
  });

  it("stamps reduced-motion state so the contract is auditable", () => {
    stubMatchMedia(true);
    const { container } = render(<WindowAdBorder windowId="w4" />);
    const border = container.querySelector("[data-window-ad-border='w4']");
    expect(border?.getAttribute("data-reduced-motion")).toBe("true");
  });

  it("border container is pointer-events:none so it never occludes the page", () => {
    const { container } = render(<WindowAdBorder windowId="w5" />);
    const border = container.querySelector("[data-window-ad-border='w5']") as HTMLElement;
    expect(border.className).toContain("pointer-events-none");
  });
});
