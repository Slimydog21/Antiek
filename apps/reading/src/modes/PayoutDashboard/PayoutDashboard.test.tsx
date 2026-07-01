import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PayoutDashboard from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      current_month_label: "2026-07",
      platform_residual_month_cents: Number.POSITIVE_INFINITY,
      unallocated_rounding_month_cents: Number.NaN,
      lines: [
        {
          recipient_kind: "creator",
          recipient_ref: "creator-bad",
          recipient_name: "Malformed Creator",
          current_month_cents: Number.NaN,
          lifetime_cents: Number.POSITIVE_INFINITY,
          status: "active",
          kyc_complete: true,
        },
        {
          recipient_kind: "publisher",
          recipient_ref: "publisher-good",
          recipient_name: "Measured Publisher",
          current_month_cents: 1234,
          lifetime_cents: 5000,
          status: "escrow_only",
          kyc_complete: false,
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

describe("PayoutDashboard", () => {
  it("sanitizes malformed dashboard payout cents", async () => {
    render(<PayoutDashboard />);

    expect(await screen.findByText("Malformed Creator")).toBeTruthy();
    expect(screen.getByText("Measured Publisher")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$12.34")).toHaveLength(2);
    expect(screen.getByText(/lifetime \$50.00/)).toBeTruthy();
  });
});
