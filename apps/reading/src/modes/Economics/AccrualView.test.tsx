/**
 * AccrualView.test — §9 surfaced honestly, never paid (Product Depth SPR-10).
 *
 * Load-bearing claims (each maps to a verification gate on the sprint page):
 *  - whose work grounds the synthesis renders from the SHIPPED Option B
 *    attribution (one model), with the IP holder shown where known (M1/M2);
 *  - every figure is "would be owed", labelled not-yet-paid; the honest today
 *    balance is $0 (M2);
 *  - NO money path: there is no disburse/pay/payout/transfer control; the only
 *    money-adjacent control ("Try a payout") refuses with the gate reason and
 *    moves no money — and never fires a host handler that would (M4, BINDING);
 *  - opt-in only: a pre_onboarded holder reads as eligible-on-opt-in, never
 *    "money waiting" against an unconsenting rights holder (§9.10);
 *  - honest no-key: when attribution can't compute, the no-result state shows,
 *    with no fabricated owed amounts (M4).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type {
  AttributionReportResponse,
  ConsentViewResponse,
} from "../../lib/api";

const { getAttributionReportMock, getConsentViewMock } = vi.hoisted(() => ({
  getAttributionReportMock: vi.fn(),
  getConsentViewMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getAttributionReport: getAttributionReportMock,
    getConsentView: getConsentViewMock,
  };
});

import AccrualView from "./AccrualView";

afterEach(() => {
  cleanup();
  getAttributionReportMock.mockReset();
  getConsentViewMock.mockReset();
});

function report(over: Partial<AttributionReportResponse> = {}): AttributionReportResponse {
  const emptyAlgo = {
    algorithm: "B" as const,
    shares: {},
    document_titles: {},
    document_count: 0,
    claim_count: 0,
    document_ip_holders: {},
    document_ip_holder_status: {},
  };
  return {
    synthesis_id: "syn-1",
    target_question: "Why does X compound?",
    option_a: { ...emptyAlgo, algorithm: "A" },
    option_b: {
      ...emptyAlgo,
      shares: { "doc-A": 0.7, "doc-B": 0.3 },
      document_titles: { "doc-A": "On Growth and Form", "doc-B": "A Blog Post" },
      document_count: 2,
      claim_count: 2,
      document_ip_holders: { "doc-A": "ip-mit", "doc-B": null },
      document_ip_holder_status: { "ip-mit": "pre_onboarded" },
    },
    option_c: { ...emptyAlgo, algorithm: "C" },
    ...over,
  };
}

function consent(over: Partial<ConsentViewResponse> = {}): ConsentViewResponse {
  return {
    holders: [],
    escrow_report: {
      pre_onboarded: 3,
      invited: 0,
      claimed: 0,
      opted_out: 0,
      claim_rate: 0,
      total_escrow_accrued_cents: 0,
      total_escrow_paid_cents: 0,
      unclaimed_escrow_cents: 0,
      publishers_with_nontrivial_accrual: 0,
    },
    disbursement_gates_open: ["G2", "G3"],
    total_escrow_accruing_usd: "0",
    any_disbursable: false,
    gate_source_path: "docs/operator_gate_actions.md",
    ...over,
  };
}

describe("AccrualView — accrual shown, never paid (M2/M4)", () => {
  it("shows whose work grounds the synthesis with the IP holder where known", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    render(<AccrualView synthesisId="syn-1" />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    expect(screen.getByText(/A Blog Post/)).toBeTruthy();
    // The model is Option B's share — 70% to doc-A.
    expect(screen.getByText(/70% of attribution/)).toBeTruthy();
  });

  it("labels every figure not-yet-paid with an honest $0 today", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    render(<AccrualView synthesisId="syn-1" />);
    await screen.findByRole("button", { name: /try a payout/i });
    expect(screen.getAllByText(/would be owed/i).length).toBeGreaterThan(0);
    // The honest "today" balance is $0, never a fabricated owed amount.
    expect(screen.getAllByText(/\$0\.00/).length).toBeGreaterThan(0);
  });

  it("frames a pre_onboarded holder as opt-in eligible, never money waiting (§9.10)", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    render(<AccrualView synthesisId="syn-1" />);
    await waitFor(() => expect(screen.getByText(/escrow-eligible once they opt in/i)).toBeTruthy());
    // The unconsenting / unknown owner reads as "no payee", not money owed.
    expect(screen.getByText(/unknown owner — no payee/i)).toBeTruthy();
    // The escrow framing is opt-in only: pay for PROSPECTIVE use once opted in,
    // and explicitly NO money waiting against anyone who hasn't.
    expect(
      screen.getByText(/no money waiting against anyone who hasn't/i),
    ).toBeTruthy();
    // No row is ever labelled with a positive owed dollar figure.
    expect(screen.queryByText(/owed[^.]*\$[1-9]/i)).toBeNull();
  });
});

describe("AccrualView — NO money path (M4, BINDING)", () => {
  it("has no disburse/pay/payout/transfer/send-money control", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    render(<AccrualView synthesisId="syn-1" />);
    await waitFor(() => expect(screen.getByText(/whose work grounds this/i)).toBeTruthy());
    // No control that would move money. "Try a payout" is the gated refusal,
    // not a money-mover — it's matched and excluded by name below.
    const buttons = await screen.findAllByRole("button");
    for (const b of buttons) {
      expect(b.textContent ?? "").not.toMatch(/disburse|send money|transfer|pay out now|withdraw/i);
    }
  });

  it("the only money-adjacent control refuses with the gate reason and moves no money", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    const onPayoutRefused = vi.fn();
    render(<AccrualView synthesisId="syn-1" onPayoutRefused={onPayoutRefused} />);
    // Wait for the control itself — the loading copy also contains
    // "whose work grounds this", which made the previous wait racey on CI.
    fireEvent.click(await screen.findByRole("button", { name: /try a payout/i }));
    // It surfaces the specific gate reason (G2 + G3) and says nothing was paid.
    expect(screen.getByText(/G2 \+ G3/)).toBeTruthy();
    expect(screen.getByText(/Nothing was paid/i)).toBeTruthy();
    // The host hook is a REFUSAL notification carrying the open gates — never a
    // disbursement trigger. It fires only on the refusal path, with the reason.
    expect(onPayoutRefused).toHaveBeenCalledOnce();
    expect(onPayoutRefused).toHaveBeenCalledWith({ openGates: ["G2", "G3"] });
  });

  it("refuses inline even with NO host handler — there is no path to a payout", async () => {
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(consent());
    render(<AccrualView synthesisId="syn-1" />); // no onPayoutRefused
    fireEvent.click(await screen.findByRole("button", { name: /try a payout/i }));
    expect(screen.getByText(/Nothing was paid/i)).toBeTruthy();
  });

  it("does NOT disburse or fire the refusal hook even if the legal gate were closed", async () => {
    // The future-unlock seam: a maintainer closes G2 + G3 (any_disbursable=true).
    // The client STILL must not disburse — real payouts come from the
    // operator-gated backend route — and the refusal hook must not fire
    // spuriously on a non-refusal. This guards the critic's single biggest risk:
    // a future host wiring this surface to real money.
    getAttributionReportMock.mockResolvedValue(report());
    getConsentViewMock.mockResolvedValue(
      consent({ disbursement_gates_open: [], any_disbursable: true }),
    );
    const onPayoutRefused = vi.fn();
    render(<AccrualView synthesisId="syn-1" onPayoutRefused={onPayoutRefused} />);
    await waitFor(() => expect(screen.getByText(/whose work grounds this/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /try a payout/i }));
    // The refusal hook is NOT a payout trigger — it stays silent off the refusal path.
    expect(onPayoutRefused).not.toHaveBeenCalled();
    // The client never disburses; it points payouts at the operator-gated route.
    expect(screen.getByText(/operator-gated backend route/i)).toBeTruthy();
    expect(screen.getByText(/Nothing was paid here/i)).toBeTruthy();
    // No fabricated positive dollar figure is ever produced as "paid".
    expect(screen.queryByText(/paid[^.]*\$[1-9]/i)).toBeNull();
  });
});

describe("AccrualView — honest no-key state (M4)", () => {
  it("shows the no-result state, no fabricated owed amounts, when attribution can't compute", async () => {
    getAttributionReportMock.mockRejectedValue(new Error("no result"));
    getConsentViewMock.mockRejectedValue(new Error("no result"));
    render(<AccrualView synthesisId="syn-1" />);
    await waitFor(() =>
      expect(screen.getByText(/couldn't work out the attribution/i)).toBeTruthy(),
    );
    // No fabricated dollar figure in the failure state.
    expect(screen.queryByText(/\$[1-9]/)).toBeNull();
    // The honest no-provider sentence (AIActionFailure, reason absent). The
    // component renders a curly apostrophe (’), so match flexibly on "provider".
    expect(screen.getByText(/model provider/i)).toBeTruthy();
    expect(screen.getByText(/check\s+provider keys/i)).toBeTruthy();
  });
});
