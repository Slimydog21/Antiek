import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PayoutsAudit from "./index";

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
      transfers: [
        {
          transfer_attempt_id: "transfer-bad",
          decision_id: "decision-bad",
          stripe_transfer_id: null,
          recipient_account_id: "acct_bad",
          amount_usd_cents: Number.NaN,
          status: "transferred",
          note: null,
          initiated_at: null,
        },
        {
          transfer_attempt_id: "transfer-good",
          decision_id: "decision-good",
          stripe_transfer_id: "tr_1",
          recipient_account_id: "acct_good",
          amount_usd_cents: 1234,
          status: "transferred",
          note: null,
          initiated_at: "2026-07-01T12:00:00Z",
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

describe("PayoutsAudit", () => {
  it("sanitizes malformed payout cents in totals and rows", async () => {
    render(<PayoutsAudit />);

    expect(await screen.findByText("acct_bad")).toBeTruthy();
    expect(screen.getByText("acct_good")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(screen.getAllByText("$12.34")).toHaveLength(2);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
  });
});
