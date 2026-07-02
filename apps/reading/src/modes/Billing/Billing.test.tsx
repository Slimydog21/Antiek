import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Billing from "./index";

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
      user_id: "__operator__",
      period: "2026-07",
      free_tokens_consumed: Number.POSITIVE_INFINITY,
      free_tokens_remaining: Number.NaN,
      paid_public_token_cost_usd: "NaN",
      paid_public_margin_usd: "Infinity",
      paid_private_token_cost_usd: "-1",
      paid_private_margin_usd: "0.125",
      total_raw_usd: "NaN",
      total_margin_usd: "Infinity",
      total_billable_usd: "12.34567",
      record_count: Number.POSITIVE_INFINITY,
    }),
  });
});

afterEach(() => cleanup());

describe("Billing", () => {
  it("sanitizes malformed billing summary numbers", async () => {
    render(<Billing />);

    expect(await screen.findByText("Free-tier usage")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(screen.getByText(/0 \/ 5,000,000 tokens · 0%/)).toBeTruthy();
    expect(screen.getByText("remaining: 0")).toBeTruthy();
    expect(screen.getAllByText("$0.0000").length).toBeGreaterThan(0);
    expect(screen.getByText("$12.3457")).toBeTruthy();
    expect(screen.getByText("0 usage records aggregated this period")).toBeTruthy();
  });

  it("normalizes billing API response fields before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        user_id: " __operator__ ",
        period: " 2026-07 ",
        free_tokens_consumed: "1234.9",
        free_tokens_remaining: "4998765.1",
        paid_public_token_cost_usd: " 0.25 ",
        paid_public_margin_usd: "0.025",
        paid_private_token_cost_usd: "bad",
        paid_private_margin_usd: "-1",
        total_raw_usd: "0.25",
        total_margin_usd: "0.025",
        total_billable_usd: "0.275",
        record_count: "2.9",
      }),
    });

    render(<Billing />);

    expect(await screen.findByText("Free-tier usage")).toBeTruthy();
    expect(screen.getByText(/1,234 \/ 5,000,000 tokens · 0%/)).toBeTruthy();
    expect(screen.getByText("remaining: 4,998,765")).toBeTruthy();
    expect(screen.getAllByText("$0.2500").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$0.0250").length).toBeGreaterThan(0);
    expect(screen.getByText("$0.2750")).toBeTruthy();
    expect(screen.getByText("2 usage records aggregated this period")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/bad|NaN|Infinity|\$-/);
  });
});
