import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  ConsentSection,
  CostSection,
  type ConsentView,
  type CostView,
} from "./CostConsent";

afterEach(() => cleanup());

const costView = (over: Partial<CostView> = {}): CostView => ({
  per_workflow: [
    {
      workflow: "research",
      raw_cost_usd: "NaN",
      call_count: 1,
      remote_exec_cost_usd: "Infinity",
      margin_status: "applied",
      margin_rate: "Infinity",
      margined_cost_usd: "NaN",
      margin_note: "malformed fixture",
    },
  ],
  aggregate_raw_cost_usd: "Infinity",
  aggregate_call_count: 1,
  aggregate_remote_exec_cost_usd: "NaN",
  has_unmapped_spend: false,
  events_dir: "/tmp/events",
  ...over,
});

const consentView = (over: Partial<ConsentView> = {}): ConsentView => ({
  holders: [
    {
      ip_holder_id: "holder-1",
      display_name: "Publisher",
      status: "claimed",
      escrow_balance_usd: "NaN",
      gate: {
        disbursable: false,
        open_gate_ids: ["G2"],
        holder_claimed: true,
        fully_unlocked: false,
        label: "blocked",
      },
      serves_full_text: false,
      servability_note: null,
    },
  ],
  escrow_report: {
    pre_onboarded: 1,
    invited: 0,
    claimed: 1,
    opted_out: 0,
    claim_rate: Number.POSITIVE_INFINITY,
    total_escrow_accrued_cents: 0,
    total_escrow_paid_cents: Number.POSITIVE_INFINITY,
    unclaimed_escrow_cents: 0,
    publishers_with_nontrivial_accrual: 0,
  },
  disbursement_gates_open: ["G2"],
  total_escrow_accruing_usd: "Infinity",
  any_disbursable: false,
  gate_source_path: "/tmp/gates.json",
  ...over,
});

describe("CostConsent", () => {
  it("sanitizes malformed cost money and margin rates", () => {
    render(<CostSection cost={costView()} />);

    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(document.body.textContent).toContain("$0.0000");
    expect(document.body.textContent).toContain("applied");
  });

  it("sanitizes malformed escrow money and claim rates", () => {
    render(<ConsentSection consent={consentView()} />);

    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(document.body.textContent).toContain("$0.0000");
    expect(document.body.textContent).toContain("$0.00");
    expect(document.body.textContent).toContain("0%");
  });
});
