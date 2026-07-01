import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MarketplaceMetrics from "./index";

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
      health: "watch",
      health_signals: ["publisher claims need work"],
      creators: {
        creator_count: Number.POSITIVE_INFINITY,
        total_paid_cents: Number.NaN,
        median_cents: 1234,
        p90_cents: Number.POSITIVE_INFINITY,
        p99_cents: -1,
        long_tail_mass: Number.NaN,
        buckets: [
          {
            lower_cents: Number.NaN,
            upper_cents: Number.POSITIVE_INFINITY,
            creator_count: Number.NaN,
          },
          {
            lower_cents: 1000,
            upper_cents: -1,
            creator_count: 2,
          },
        ],
      },
      publishers: {
        status_counts: {
          pre_onboarded: Number.NaN,
          invited: Number.POSITIVE_INFINITY,
          claimed: 2,
          opted_out: -1,
          total: Number.NaN,
          claim_rate: Number.POSITIVE_INFINITY,
          opt_out_rate: Number.NaN,
        },
        total_escrow_accrued_cents: Number.POSITIVE_INFINITY,
        total_escrow_paid_cents: 500,
        unclaimed_escrow_cents: Number.NaN,
        publishers_with_nontrivial_accrual: 0,
      },
      advertisers: {
        advertiser_count_current: Number.NaN,
        advertiser_count_prior: 4,
        retained_advertiser_count: Number.POSITIVE_INFINITY,
        new_advertiser_count: -1,
        churned_advertiser_count: 1,
        total_spend_current_cents: 2500,
        total_spend_prior_cents: Number.NaN,
        retention_rate: Number.NaN,
        crosses_self_service_threshold: false,
      },
    }),
  });
});

afterEach(() => cleanup());

describe("MarketplaceMetrics", () => {
  it("sanitizes malformed marketplace health metrics", async () => {
    render(<MarketplaceMetrics />);

    expect(await screen.findByText("Marketplace health")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-|-%/);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
    expect(screen.getByText("$12.34")).toBeTruthy();
    expect(screen.getByText("$25.00")).toBeTruthy();
    expect(screen.getAllByText("0.0%").length).toBeGreaterThan(0);
    expect(screen.getByText("$10.00+")).toBeTruthy();
  });
});
