import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import PayoutsAudit, { PayoutAuditView, type PayoutRow } from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
afterEach(cleanup);
const transferred: PayoutRow = { transfer_attempt_id: "xfer-1", decision_id: "decision-1", stripe_transfer_id: "tr_1", recipient_account_id: "acct_1", amount_usd_cents: 12500, status: "transferred", note: "transferred via Stripe Connect", initiated_at: "2026-07-14T10:00:00Z" };
const held: PayoutRow = { ...transferred, transfer_attempt_id: "xfer-2", decision_id: "decision-2", stripe_transfer_id: null, amount_usd_cents: 6400, status: "skipped_escrow", note: "publisher pre-onboarded" };
const callbacks = { onFilterChange: vi.fn(), onRecipientChange: vi.fn(), onApply: vi.fn(), onClear: vi.fn(), onRetry: vi.fn() };
const response = (body: unknown, ok = true) => ({ ok, json: vi.fn().mockResolvedValue(body) }) as unknown as Response;

describe("Payout Signal House", () => {
  beforeEach(() => vi.clearAllMocks());
  it("states the query, settlement, reconciliation, and empty-response limits", () => {
    render(<PayoutAuditView rows={[]} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.getByText(/capped at 500 newest matching rows/i)).toBeTruthy();
    expect(screen.getByText(/does not prove settlement/i)).toBeTruthy();
    expect(screen.getByText(/cannot distinguish those cases yet/i)).toBeTruthy();
  });
  it("separates provider-accepted amounts from escrow holds", () => {
    render(<PayoutAuditView rows={[transferred, held]} filter="all" recipientFilter="" {...callbacks} />);
    const summary = screen.getByRole("heading", { name: /2 recorded outcomes/i }).closest("section")!;
    expect(within(summary).getAllByText("$125.00")).toHaveLength(2);
    expect(within(summary).getByText("$64.00")).toBeTruthy();
    expect(screen.getByText(/no provider transfer fired/i)).toBeTruthy();
  });
  it("does not promote transferred rows without a provider identifier", () => {
    render(<PayoutAuditView rows={[{ ...transferred, stripe_transfer_id: null }]} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.getByText("Transfer unverified")).toBeTruthy();
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
    expect(screen.getByText(/no provider transfer identifier/i)).toBeTruthy();
  });
  it("does not render raw provider exception notes", () => {
    render(<PayoutAuditView rows={[{ ...transferred, status: "failed", stripe_transfer_id: null, note: "provider error: secret_token=do-not-render" }]} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.queryByText(/secret_token/i)).toBeNull();
    expect(screen.getByText(/protected transport diagnostics/i)).toBeTruthy();
  });
  it("bounds invalid timestamps", () => {
    render(<PayoutAuditView rows={[{ ...transferred, initiated_at: "not-a-time" }]} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.getByText("Time not reported")).toBeTruthy();
  });
  it("labels an unrecognized future status without crashing", () => {
    render(<PayoutAuditView rows={[{ ...transferred, status: "future_state" }]} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.getByText("Unrecognized status")).toBeTruthy();
  });
  it("announces when the 500-row response cap is reached", () => {
    render(<PayoutAuditView rows={Array.from({ length: 500 }, (_, index) => ({ ...transferred, transfer_attempt_id: `xfer-${index}`, decision_id: `decision-${index}` }))} filter="all" recipientFilter="" {...callbacks} />);
    expect(screen.getByRole("status").textContent).toMatch(/older matching records may exist/i);
  });
  it("loads the initial bounded query", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ transfers: [transferred] }));
    render(<PayoutsAudit />);
    expect(await screen.findByText(/1 recorded outcomes/i)).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith("/payouts/transfers?limit=500");
  });
  it("applies filters explicitly and encodes the exact recipient", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ transfers: [] }));
    render(<PayoutsAudit />);
    await screen.findByText(/no rows returned/i);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
    fireEvent.change(screen.getByLabelText(/exact recipient account/i), { target: { value: " acct_A&B " } });
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    await waitFor(() => expect(apiFetch).toHaveBeenLastCalledWith("/payouts/transfers?limit=500&status=failed&recipient_account_id=acct_A%26B"));
  });
  it("rejects a malformed successful payload instead of inferring empty", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ transfers: [{ status: "transferred" }] }));
    render(<PayoutsAudit />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/unavailable or malformed/i);
    expect(screen.queryByText(/0 recorded outcomes/i)).toBeNull();
  });
  it("ignores stale responses after a newer query", async () => {
    let resolveFirst!: (value: Response) => void;
    vi.mocked(apiFetch).mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; })).mockResolvedValueOnce(response({ transfers: [held] }));
    render(<PayoutsAudit />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "skipped_escrow" } });
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(await screen.findByText(/1 recorded outcomes/i)).toBeTruthy();
    resolveFirst(response({ transfers: [transferred] }));
    await waitFor(() => expect(screen.getByText("Held in escrow")).toBeTruthy());
    const ledger = screen.getByRole("heading", { name: "Transfer ledger" }).closest("section")!;
    expect(within(ledger).queryByText("Provider accepted")).toBeNull();
    expect(within(ledger).getByText("Held in escrow")).toBeTruthy();
  });
});
