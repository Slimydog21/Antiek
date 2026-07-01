import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CreatorPayouts from "./index";

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
      user_id: "user-1",
      current_balance_cents: Number.NaN,
      minimum_payout_cents: Number.POSITIVE_INFINITY,
      rollover_state: "accruing",
      rollover_started_month: null,
      total_paid_cents: -1,
      transfers: [
        {
          transfer_attempt_id: "transfer-bad",
          stripe_transfer_id: null,
          amount_usd_cents: Number.NaN,
          status: "pending",
          initiated_at: null,
          note: null,
        },
        {
          transfer_attempt_id: "transfer-good",
          stripe_transfer_id: "tr_1",
          amount_usd_cents: 1234,
          status: "transferred",
          initiated_at: "2026-07-01T12:00:00Z",
          note: null,
        },
      ],
      accrual_history: [
        {
          at: "2026-07",
          kind: "ad_share",
          cents: Number.POSITIVE_INFINITY,
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

describe("CreatorPayouts", () => {
  it("sanitizes malformed balances, transfers, and accrual entries", async () => {
    render(<CreatorPayouts />);

    expect(await screen.findByText("Current balance")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(screen.getByText("$12.34")).toBeTruthy();
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
  });
});
