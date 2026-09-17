/**
 * ManualSponsorFooter — flag-gated MASTER.md sponsor rail (website ads MVP).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import ManualSponsorFooter from "./ManualSponsorFooter";
import { BIDDING_POLICY_MANUAL_SPONSOR } from "./manualSponsorFill";

vi.mock("./manualSponsorFill", async (orig) => {
  const actual = await orig<typeof import("./manualSponsorFill")>();
  return {
    ...actual,
    resolveManualSponsorFill: vi.fn(() => ({ kind: "house", house: null })),
  };
});

afterEach(cleanup);

describe("ManualSponsorFooter", () => {
  it("renders nothing when the flag is off (default)", () => {
    render(<ManualSponsorFooter synthesisId="syn-1" enabled={false} />);
    expect(screen.queryByTestId("manual-sponsor-footer")).toBeNull();
    expect(screen.queryByLabelText("Recommended reading")).toBeNull();
  });

  it("mounts AdBorder house rail when enabled, tagged MANUAL_SPONSOR", () => {
    render(<ManualSponsorFooter synthesisId="syn-1" enabled />);
    const root = screen.getByTestId("manual-sponsor-footer");
    expect(root.getAttribute("data-bidding-policy")).toBe(
      BIDDING_POLICY_MANUAL_SPONSOR,
    );
    // House honesty from AdBorder / HouseSlot
    expect(screen.getByText("From the library")).toBeTruthy();
    expect(screen.getByLabelText("Recommended reading")).toBeTruthy();
    const rail = screen.getByLabelText("Recommended reading");
    expect(rail.getAttribute("data-slot-id")).toBe(
      "slot:synthesis:syn-1:footer",
    );
    expect(rail.getAttribute("data-slot-position")).toBe("bottom");
  });

  it("uses anon slot id when synthesisId is missing", () => {
    render(<ManualSponsorFooter enabled />);
    expect(
      screen.getByLabelText("Recommended reading").getAttribute("data-slot-id"),
    ).toBe("slot:synthesis:anon:footer");
  });
});
