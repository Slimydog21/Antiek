import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OperatorDashboard from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

const okJson = (body: unknown) =>
  ({
    ok: true,
    json: async () => body,
  }) as Response;

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/publishers") {
      return okJson({
        publishers: [
          {
            ip_holder_id: "holder-bad",
            display_name: "Malformed Publisher",
            legal_contact_email: null,
            status: "pre_onboarded",
            escrow_balance_usd: "NaN",
            notification_sent_at: null,
            claimed_at: null,
            opted_out_at: null,
          },
        ],
      });
    }
    if (path === "/stats") {
      return okJson({
        counts: {
          investigations: Number.POSITIVE_INFINITY,
          notebooks: Number.NaN,
          outcomes: -4,
          skill_rules: "1500.8",
          payout_transfers: "bad",
          ip_holders: 1,
        },
        warnings: [],
      });
    }
    if (path === "/trust-center/deletion-requests") {
      return okJson({ requests: [{ request_id: "dr-1", status: "pending" }] });
    }
    if (path.startsWith("/payouts/transfers")) {
      return okJson({
        transfers: [
          {
            status: "transferred",
            amount_usd_cents: Number.POSITIVE_INFINITY,
            initiated_at: null,
          },
          {
            status: "failed",
            amount_usd_cents: 250,
            initiated_at: "2026-07-01T12:00:00Z",
          },
        ],
      });
    }
    return okJson({});
  });
});

afterEach(() => cleanup());

describe("OperatorDashboard", () => {
  it("sanitizes malformed payout, escrow, and snapshot metrics", async () => {
    render(
      <MemoryRouter>
        <OperatorDashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Malformed Publisher")).toBeTruthy();
    expect(screen.getByText("transferred")).toBeTruthy();
    expect(screen.getByText("failed")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-|-4/);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
    expect(screen.getByText("$2.50")).toBeTruthy();
    expect(screen.getByText("1,500")).toBeTruthy();
  });
});
