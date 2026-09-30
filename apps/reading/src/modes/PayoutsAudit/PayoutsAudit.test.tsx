import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import PayoutsAudit from "./index";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const STATUSES = ["transferred", "skipped escrow", "skipped platform", "failed", "pending"];

const transferred = {
  transfer_attempt_id: "ta-1",
  decision_id: "dec-1",
  stripe_transfer_id: "tr_1",
  recipient_account_id: "acct_mit",
  amount_usd_cents: 1234,
  status: "transferred",
  note: null,
  initiated_at: "2026-09-01T00:00:00Z",
};

/** The count shown in a status tile (the tile label is the only <p> with that text). */
function tileCount(label: string): string | null {
  const labelEl = screen.getAllByText(label).find((el) => el.tagName === "P");
  return labelEl?.previousElementSibling?.textContent ?? null;
}

beforeEach(() => {
  apiFetchMock.mockReset();
});
afterEach(cleanup);

describe("PayoutsAudit — a failed load is an unknown", () => {
  it("while the log is loading, no tile states a count", () => {
    apiFetchMock.mockReturnValue(new Promise<Response>(() => {}));
    render(<PayoutsAudit />);
    for (const s of STATUSES) expect(tileCount(s)).toBe("…");
    expect(screen.queryByText("$0.00")).toBeNull();
  });

  it("a failed load shows no totals and no empty list, and Try again loads the log", async () => {
    // Rubric veto: five 0 / $0.00 tiles beside a raw "HTTP 404" banner.
    apiFetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(response({ transfers: [transferred] }));
    render(<PayoutsAudit />);

    const failure = await screen.findByText("Transfers didn't load.");
    expect(failure.getAttribute("title")).toBe("Failed to fetch");
    for (const s of STATUSES) expect(tileCount(s)).toBe("—");
    expect(screen.queryByText("$0.00")).toBeNull();
    expect(screen.queryByText("No transfers match this filter.")).toBeNull();
    expect(document.body.textContent).not.toContain("Failed to fetch");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("acct_mit")).toBeTruthy();
    expect(tileCount("transferred")).toBe("1");
    expect(tileCount("failed")).toBe("0");
    expect(screen.queryByText("Transfers didn't load.")).toBeNull();
  });

  it("a failed reload after a filter change drops the previous filter's totals", async () => {
    apiFetchMock
      .mockResolvedValueOnce(response({ transfers: [transferred] }))
      .mockResolvedValueOnce(response({}, 502));
    render(<PayoutsAudit />);
    expect(await screen.findByText("acct_mit")).toBeTruthy();
    expect(tileCount("transferred")).toBe("1");

    fireEvent.click(screen.getByRole("button", { name: "failed" }));

    const failure = await screen.findByText("Transfers didn't load.");
    expect(failure.getAttribute("title")).toContain("HTTP 502");
    for (const s of STATUSES) expect(tileCount(s)).toBe("—");
    expect(screen.queryByText("acct_mit")).toBeNull();
    expect(document.body.textContent).not.toContain("HTTP 502");
  });
});
