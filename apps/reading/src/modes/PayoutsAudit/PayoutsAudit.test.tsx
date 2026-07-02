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

  it("normalizes payout transfer rows before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        transfers: [
          {
            transfer_attempt_id: " transfer dirty ",
            decision_id: " decision dirty ",
            stripe_transfer_id: " tr_dirty ",
            recipient_account_id: " acct_dirty ",
            amount_usd_cents: "1250.9",
            status: " transferred ",
            note: " paid ",
            initiated_at: " 2026-07-02T02:00:00Z ",
          },
          {
            transfer_attempt_id: " ",
            decision_id: "decision-skipped",
            recipient_account_id: "Skipped transfer",
          },
          {
            transfer_attempt_id: "transfer-skipped",
            decision_id: " ",
            recipient_account_id: "Skipped decision",
          },
        ],
      }),
    });

    render(<PayoutsAudit />);

    expect(await screen.findByText("acct_dirty")).toBeTruthy();
    expect(screen.getByText(/decision=decision dirty/)).toBeTruthy();
    expect(screen.getByText(/stripe=tr_dirty/)).toBeTruthy();
    expect(screen.getByText("paid")).toBeTruthy();
    expect(screen.getAllByText("$12.50").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("2026-07-02T02:00:00Z")).toBeTruthy();
    expect(screen.queryByText("Skipped transfer")).toBeNull();
    expect(screen.queryByText("Skipped decision")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-|Skipped/);
  });
});
