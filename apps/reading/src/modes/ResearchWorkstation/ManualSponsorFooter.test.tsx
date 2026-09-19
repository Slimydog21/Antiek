/**
 * ManualSponsorFooter — flag-gated MASTER.md sponsor rail (website ads MVP).
 * Ledger path: POST /api/ad/fills via fillFetcher (dual structure).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import type { FillResult } from "../../components/ad/adFillClient";
import ManualSponsorFooter from "./ManualSponsorFooter";
import { BIDDING_POLICY_MANUAL_SPONSOR } from "./manualSponsorFill";

afterEach(cleanup);

function houseResult(): FillResult {
  return {
    served: true,
    fills: [
      {
        fill_decision_id: "fill-abc:bottom",
        slot_id: "slot:fill-abc:bottom",
        position: "bottom",
        kind: "house",
        ad: null,
        house: null,
        revenue_usd_cents: 0,
        price_status: "unpriced",
      },
    ],
  };
}

function sponsorResult(): FillResult {
  return {
    served: true,
    fills: [
      {
        fill_decision_id: "fill-sponsor:bottom",
        slot_id: "slot:fill-sponsor:bottom",
        position: "bottom",
        kind: "ad",
        ad: {
          inventory_id: "manual_sponsor:operator",
          advertiser_display_name: "Acme Labs",
          creative_url: "https://example.com/mark.png",
          landing_url: "https://example.com/",
        },
        house: null,
        revenue_usd_cents: 0,
        price_status: "unpriced",
      },
    ],
  };
}

describe("ManualSponsorFooter", () => {
  it("renders nothing when the flag is off (default)", () => {
    render(<ManualSponsorFooter synthesisId="syn-1" enabled={false} />);
    expect(screen.queryByTestId("manual-sponsor-footer")).toBeNull();
    expect(screen.queryByLabelText("Recommended reading")).toBeNull();
  });

  it("mounts AdBorder house rail when enabled, tags MANUAL_SPONSOR + ledger attrs", async () => {
    const fillFetcher = vi.fn(async () => houseResult());
    render(
      <ManualSponsorFooter synthesisId="syn-1" enabled fillFetcher={fillFetcher} />,
    );
    const root = await screen.findByTestId("manual-sponsor-footer");
    expect(root.getAttribute("data-bidding-policy")).toBe(
      BIDDING_POLICY_MANUAL_SPONSOR,
    );
    await waitFor(() => {
      expect(root.getAttribute("data-fill-served")).toBe("1");
      expect(root.getAttribute("data-fill-decision-id")).toBe("fill-abc:bottom");
    });
    expect(fillFetcher).toHaveBeenCalledWith(
      expect.objectContaining({
        windowId: "win:research:manual-sponsor:syn-1",
        lens: "research",
        positions: ["bottom"],
      }),
    );
    expect(screen.getByText("From the library")).toBeTruthy();
    await waitFor(() => {
      expect(root.getAttribute("data-price-status")).toBe("unpriced");
      expect(root.getAttribute("data-fill-kind")).toBe("house");
    });
    expect(screen.getByTestId("manual-sponsor-rank0-honesty").textContent).toMatch(
      /House fill/,
    );
    const rail = screen.getByLabelText("Recommended reading");
    expect(rail.getAttribute("data-slot-id")).toBe(
      "slot:synthesis:syn-1:footer",
    );
    expect(rail.getAttribute("data-slot-position")).toBe("bottom");
  });

  it("renders sponsor creative when fills return a manual_sponsor ad", async () => {
    const fillFetcher = vi.fn(async () => sponsorResult());
    render(
      <ManualSponsorFooter synthesisId="syn-2" enabled fillFetcher={fillFetcher} />,
    );
    expect(await screen.findByText("Acme Labs")).toBeTruthy();
    expect(screen.getByLabelText("Advertisement")).toBeTruthy();
    const root = screen.getByTestId("manual-sponsor-footer");
    await waitFor(() => {
      expect(root.getAttribute("data-price-status")).toBe("unpriced");
      expect(root.getAttribute("data-fill-kind")).toBe("ad");
    });
    expect(screen.getByTestId("manual-sponsor-rank0-honesty").textContent).toMatch(
      /Sponsor fill/,
    );
  });

  it("uses anon slot id when synthesisId is missing", async () => {
    const fillFetcher = vi.fn(async () => houseResult());
    render(<ManualSponsorFooter enabled fillFetcher={fillFetcher} />);
    await waitFor(() => {
      expect(
        screen.getByLabelText("Recommended reading").getAttribute("data-slot-id"),
      ).toBe("slot:synthesis:anon:footer");
    });
    expect(fillFetcher).toHaveBeenCalledWith(
      expect.objectContaining({
        windowId: "win:research:manual-sponsor:anon",
      }),
    );
  });
});
