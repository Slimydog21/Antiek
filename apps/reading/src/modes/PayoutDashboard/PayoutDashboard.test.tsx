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

  it("normalizes payout rows before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        current_month_label: " 2026-07 ",
        platform_residual_month_cents: " 250 ",
        unallocated_rounding_month_cents: "3.9",
        lines: [
          {
            recipient_kind: "creator",
            recipient_ref: " creator dirty ",
            recipient_name: " ",
            current_month_cents: "1250.9",
            lifetime_cents: "2000",
            status: " pending_kyc ",
            kyc_complete: "yes",
          },
          {
            recipient_kind: "publisher",
            recipient_ref: " ",
            recipient_name: "Skipped recipient",
          },
          {
            recipient_kind: "platform",
            recipient_ref: "bad-kind",
            recipient_name: "Skipped kind",
          },
        ],
      }),
    });

    render(<PayoutDashboard />);

    expect(await screen.findByText("creator dirty")).toBeTruthy();
    expect(screen.queryByText("Skipped recipient")).toBeNull();
    expect(screen.queryByText("Skipped kind")).toBeNull();
    expect(screen.getAllByText("creator").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("pending_kyc")).toBeTruthy();
    expect(screen.getByText(/KYC incomplete/)).toBeTruthy();
    expect(screen.getByText("Platform residual (month)")).toBeTruthy();
    expect(screen.getAllByText("$12.50").length).toBeGreaterThan(0);
    expect(screen.getByText(/lifetime \$20.00/)).toBeTruthy();
    expect(screen.getByText(/Unallocated rounding this month:/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-|Skipped/);
  });
});
