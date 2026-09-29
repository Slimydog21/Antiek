/**
 * AdBorder.test.tsx — SPR-07 M2/M5/M6 acceptance.
 *
 * The border wraps the working region without interfering with it. These tests
 * assert the non-interference invariants (rather than eyeballing them):
 *  - the border container is pointer-events:none (it never intercepts a
 *    click/scroll meant for the working region) and carries no tabindex (it is
 *    not in the tab order — focus flows to content first);
 *  - each rail re-enables pointer events on ITSELF only (its creative link is
 *    clickable) — the working region under it is not occluded because the rail
 *    lives in the reserved inset band;
 *  - it SETS the SPR-06 `--akb-border-inset-*` var for its one slot (so the
 *    seam frame shrinks the working region), releases the other edges, and
 *    clears them to 0 on unmount (no phantom inset);
 *  - it renders ONE labelled slot at every width (design spec §5; it used
 *    to wrap the app in four rails whose side text clipped);
 *  - house fill is the DEFAULT (no advertiser → a real house card, never
 *    blank), and it renders no animation regardless of motion preference
 *    (static creatives, reduced-motion-safe by construction).
 *
 * useViewportTier reads window.innerWidth at mount; we set it per test before
 * rendering. The 1 Hz sampler is disabled (samplingEnabled=false) so these
 * stay pure render tests with no timers.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";

import { AdBorder } from "./AdBorder";
import type { BorderPosition, FillResult } from "./adFillClient";

function setWidth(px: number): void {
  Object.defineProperty(window, "innerWidth", { value: px, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
}

/** jsdom has no matchMedia; stub it so usePrefersReducedMotion can mount.
 *  `reduce` controls whether prefers-reduced-motion: reduce matches. */
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

/** A fill fetcher that always returns house fills for the requested edges. */
async function houseFetcher(opts: { windowId: string; positions: BorderPosition[] }): Promise<FillResult> {
  return {
    fills: opts.positions.map((position) => ({
      fill_decision_id: "local-house",
      slot_id: `local:${position}`,
      position,
      kind: "house" as const,
      ad: null,
      house: null,
      revenue_usd_cents: 0,
      price_status: "unpriced" as const,
    })),
    served: false,
  };
}

beforeEach(() => stubMatchMedia(false));

afterEach(() => {
  cleanup();
  const root = document.documentElement;
  (["top", "right", "bottom", "left"] as BorderPosition[]).forEach((s) =>
    root.style.removeProperty(`--akb-border-inset-${s}`),
  );
});

describe("AdBorder — non-interference (M6)", () => {
  beforeEach(() => setWidth(1400)); // xl: all four edges

  it("renders a pointer-events:none container with no tabindex", () => {
    const { container } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    const border = container.querySelector("[data-akb-ad-border]") as HTMLElement;
    expect(border).toBeTruthy();
    expect(border.className).toContain("pointer-events-none");
    expect(border.hasAttribute("tabindex")).toBe(false);
  });

  it("binds fill authority to the same telemetry window", async () => {
    const fetcher = vi.fn(houseFetcher);
    render(<AdBorder lens="read" windowId="window-authority" samplingEnabled={false} fillFetcher={fetcher} />);
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(fetcher.mock.calls[0][0].windowId).toBe("window-authority");
  });

  it("re-enables pointer events on each rail only (its link is clickable)", () => {
    const { container } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    const rails = container.querySelectorAll("[data-akb-ad-edge]");
    expect(rails.length).toBeGreaterThan(0);
    rails.forEach((r) => expect((r as HTMLElement).className).toContain("pointer-events-auto"));
  });

  it("contains no tabbable element that would trap focus before content", () => {
    const { container } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    // No element inside the border carries a positive tabindex (which would
    // jump ahead of the working region in the tab order).
    const positive = container.querySelectorAll('[tabindex]:not([tabindex="-1"]):not([tabindex="0"])');
    expect(positive.length).toBe(0);
  });
});

describe("AdBorder — one labelled slot (design spec §5)", () => {
  // The border used to wrap the app in four rails ("Times-Square"), the side
  // rails 96px wide and clipping their text ("ore the antiek li"). The design
  // spec allows ONE labelled house-ad slot in one designated rail. The seam
  // contract is unchanged: the slot reserves its band through the SPR-06
  // --akb-border-inset-* vars, and every other edge is released to 0.
  it.each([1400, 800, 390])("renders exactly one slot, on the top edge, at %ipx", (w) => {
    setWidth(w);
    const { container } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    const slots = container.querySelectorAll("[data-akb-ad-edge]");
    expect(slots.length).toBe(1);
    expect(slots[0].getAttribute("data-akb-ad-edge")).toBe("top");
  });

  it("reserves only the slot's band and releases the other three edges", () => {
    setWidth(1400);
    render(<AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />);
    const s = document.documentElement.style;
    expect(s.getPropertyValue("--akb-border-inset-top")).toBe("32px");
    expect(s.getPropertyValue("--akb-border-inset-bottom")).toBe("0px");
    expect(s.getPropertyValue("--akb-border-inset-left")).toBe("0px");
    expect(s.getPropertyValue("--akb-border-inset-right")).toBe("0px");
  });

  it("asks the fill route for exactly the one slot it shows", async () => {
    setWidth(1400);
    const fetcher = vi.fn(houseFetcher);
    render(<AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={fetcher} />);
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(fetcher.mock.calls[0][0].positions).toEqual(["top"]);
  });

  it("labels the slot and draws it in hairline, never in sun", async () => {
    setWidth(1400);
    const { container, findByText } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    expect(await findByText("Sponsored · house")).toBeTruthy();
    const slot = container.querySelector("[data-akb-ad-edge]") as HTMLElement;
    expect(slot.getAttribute("aria-label")).toBe("Sponsored");
    expect(slot.outerHTML).not.toContain("border-sun");
    expect(slot.className).toContain("border-hairline");
  });

  it("clears the inset to 0 on unmount (no phantom inset left behind)", () => {
    setWidth(1400);
    const { unmount } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    expect(document.documentElement.style.getPropertyValue("--akb-border-inset-top")).toBe("32px");
    unmount();
    (["top", "right", "bottom", "left"] as BorderPosition[]).forEach((side) =>
      expect(document.documentElement.style.getPropertyValue(`--akb-border-inset-${side}`)).toBe("0px"),
    );
  });
});

describe("AdBorder — house fill is the default (M5)", () => {
  beforeEach(() => setWidth(1400));

  it("renders a real house card (the library on-ramp) when no advertiser matched", async () => {
    const { findAllByText } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    // Neutral house promo (no HousePromo payload) → the library on-ramp link.
    const links = await findAllByText("Explore the Antiek library");
    expect(links.length).toBeGreaterThan(0);
  });

  it("marks the border reduced-motion when prefers-reduced-motion: reduce matches (static creatives)", () => {
    stubMatchMedia(true);
    const { container } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={houseFetcher} />,
    );
    const border = container.querySelector("[data-akb-ad-border]") as HTMLElement;
    expect(border.getAttribute("data-reduced-motion")).toBe("true");
    // The creatives carry no animation/transition class regardless — static by
    // construction. No element inside the border declares an animate-* class.
    expect(container.querySelectorAll("[class*='animate-']").length).toBe(0);
  });

  it("renders a matched advertiser creative as Sponsored when a fill is served", async () => {
    const adFetcher = async (opts: { positions: BorderPosition[] }): Promise<FillResult> => ({
      fills: opts.positions.map((position) => ({
        fill_decision_id: "fd-1",
        slot_id: `slot:${position}`,
        position,
        kind: "ad" as const,
        ad: {
          inventory_id: "inv-1",
          advertiser_display_name: "Vertical SaaS Inc.",
          creative_url: "https://example.com/c.png",
          landing_url: "https://example.com/?ref=antiek",
        },
        house: null,
        revenue_usd_cents: 0,
        price_status: "unpriced" as const,
      })),
      served: true,
    });
    const { findAllByText } = render(
      <AdBorder lens="read" windowId="w1" samplingEnabled={false} fillFetcher={adFetcher} />,
    );
    expect((await findAllByText("Sponsored")).length).toBeGreaterThan(0);
    expect((await findAllByText("Vertical SaaS Inc.")).length).toBeGreaterThan(0);
  });
});
