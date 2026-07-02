import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import {
  ConsentSection,
  CostSection,
  default as CostConsent,
  type ConsentView,
  type CostView,
} from "./CostConsent";

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

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

  it("renders contextual Speak margins as applied money instead of a stub", () => {
    render(
      <CostSection
        cost={costView({
          per_workflow: [
            {
              workflow: "speak",
              raw_cost_usd: "0.40",
              call_count: 1,
              remote_exec_cost_usd: "0",
              margin_status: "applied",
              margin_rate: "0.10",
              margined_cost_usd: "0.440",
              margin_note:
                "Speak economics matrix applied from investigation policy context at 10%.",
            },
          ],
          aggregate_raw_cost_usd: "0.40",
          aggregate_call_count: 1,
          aggregate_remote_exec_cost_usd: "0",
        })}
      />,
    );

    expect(screen.getByText("Speak")).toBeTruthy();
    expect(screen.getByText("$0.4400")).toBeTruthy();
    expect(screen.getByText("+10%")).toBeTruthy();
    expect(screen.queryByText("stubbed")).toBeNull();
  });

  it("sanitizes malformed escrow money and claim rates", () => {
    render(<ConsentSection consent={consentView()} />);

    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(document.body.textContent).toContain("$0.0000");
    expect(document.body.textContent).toContain("$0.00");
    expect(document.body.textContent).toContain("0%");
  });

  it("sanitizes cost and consent API responses before rendering", async () => {
    apiFetchMock.mockImplementation(async (input) => {
      const path = String(input);
      if (path === "/coordination/cost") {
        return {
          ok: true,
          json: async () => ({
            per_workflow: [
              {
                workflow: " read ",
                raw_cost_usd: " 0.25 ",
                call_count: "2.9",
                remote_exec_cost_usd: -1,
                margin_status: "unexpected",
                margin_rate: "Infinity",
                margined_cost_usd: "NaN",
              },
              {
                workflow: " ",
                raw_cost_usd: "999",
              },
            ],
            aggregate_raw_cost_usd: " 0.25 ",
            aggregate_call_count: "2.9",
            aggregate_remote_exec_cost_usd: "Infinity",
            has_unmapped_spend: "yes",
            events_dir: " /tmp/events ",
          }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          holders: [
            {
              ip_holder_id: " holder dirty ",
              display_name: " ",
              status: " invited ",
              escrow_balance_usd: "Infinity",
              gate: {
                disbursable: true,
                open_gate_ids: [" G2 ", " "],
                holder_claimed: true,
                fully_unlocked: false,
                label: " ",
              },
              serves_full_text: "yes",
              servability_note: " gated until consent ",
            },
            {
              ip_holder_id: " ",
              display_name: "Skipped holder",
            },
          ],
          escrow_report: {
            claim_rate: "Infinity",
            total_escrow_paid_cents: "Infinity",
          },
          disbursement_gates_open: [" G2 ", " "],
          total_escrow_accruing_usd: "NaN",
          any_disbursable: "yes",
          gate_source_path: " /tmp/gates.md ",
        }),
      } as Response;
    });

    render(<CostConsent />);

    expect(await screen.findByText("Read")).toBeTruthy();
    expect(screen.getByText("holder dirty")).toBeTruthy();
    expect(screen.queryByText("Skipped holder")).toBeNull();
    expect(screen.getByText("disbursement gated on G2")).toBeTruthy();
    expect(screen.getAllByText("not disbursable").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("disbursable")).toBeNull();
    expect(screen.getByText("not surfaced here")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(document.body.textContent).not.toContain("Unclassified");
    expect(document.body.textContent).not.toContain("Some spend could not be attributed");
  });
});
