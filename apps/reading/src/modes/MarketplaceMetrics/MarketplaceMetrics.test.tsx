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

  it("normalizes marketplace snapshot rows before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        health: "unknown",
        health_signals: [" creator retention thin ", "", 42],
        creators: {
          creator_count: "2.9",
          total_paid_cents: "2500.9",
          median_cents: "1000",
          p90_cents: "2000",
          p99_cents: "bad",
          long_tail_mass: "0.125",
          buckets: [
            {
              lower_cents: "1000",
              upper_cents: "2000",
              creator_count: "3.9",
            },
            {
              lower_cents: " ",
              upper_cents: -1,
              creator_count: "1",
            },
          ],
        },
        publishers: {
          status_counts: {
            pre_onboarded: "1",
            invited: "2.8",
            claimed: "3",
            opted_out: "bad",
            total: "6",
            claim_rate: "0.5",
            opt_out_rate: "0.125",
          },
          total_escrow_accrued_cents: "1000",
          total_escrow_paid_cents: "250",
          unclaimed_escrow_cents: "750",
          publishers_with_nontrivial_accrual: "2",
        },
        advertisers: {
          advertiser_count_current: "4",
          advertiser_count_prior: "8",
          retained_advertiser_count: "3",
          new_advertiser_count: "1",
          churned_advertiser_count: "5",
          total_spend_current_cents: "5000",
          total_spend_prior_cents: "2500",
          retention_rate: "0.375",
          crosses_self_service_threshold: "yes",
        },
      }),
    });

    render(<MarketplaceMetrics />);

    expect(await screen.findByText("Marketplace health")).toBeTruthy();
    expect(screen.getByText("WATCH")).toBeTruthy();
    expect(screen.getByText("· creator retention thin")).toBeTruthy();
    expect(screen.getAllByText("$25.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("$20.00")).toBeTruthy();
    expect(screen.getAllByText("12.5%").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("$10.00 – $19.99")).toBeTruthy();
    expect(screen.getByText("3 creators")).toBeTruthy();
    expect(screen.getByText("$0.00+")).toBeTruthy();
    expect(screen.getByText("50.0%")).toBeTruthy();
    expect(screen.getByText("37.5%")).toBeTruthy();
    expect(screen.getByText("Not crossed")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/unknown|bad|NaN|Infinity|\$-|-%/);
  });
});
