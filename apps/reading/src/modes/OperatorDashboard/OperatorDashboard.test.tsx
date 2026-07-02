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
            ip_holder_id: " holder-bad ",
            display_name: " Malformed Publisher ",
            legal_contact_email: null,
            status: "pre_onboarded",
            escrow_balance_usd: "NaN",
            notification_sent_at: null,
            claimed_at: null,
            opted_out_at: null,
          },
          {
            ip_holder_id: " ",
            display_name: "Skipped Publisher",
            status: "pre_onboarded",
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
          " ": 99,
        },
        warnings: [{ message: "leaky stats warning" }],
      });
    }
    if (path === "/trust-center/deletion-requests") {
      return okJson({
        requests: [
          { request_id: "dr-1", status: " pending " },
          { request_id: "dr-2", status: "pending" },
          { request_id: "dr-3", status: "PENDING" },
        ],
      });
    }
    if (path.startsWith("/payouts/transfers")) {
      return okJson({
        transfers: [
          {
            status: " transferred ",
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
    if (path === "/coordination/roadmap") {
      return okJson({
        operator_gate_focus: {
          gate_id: " G2 ",
          title: " Counsel review ",
          status_raw: " OPEN ",
          owner: " Legal ",
          blocks: " payouts ",
        },
        read_activation: {
          valid_sessions: "1",
          total_sessions: "2.9",
          live_provider_sessions: "0",
          citation_trace_sessions: "1",
          non_library_sessions: "0",
          final_verdict: " ",
          closure_ready: "true",
          remaining_requirements: {
            valid_sessions: "9",
            live_provider_sessions: "5",
            citation_trace_sessions: "2",
            non_library_sessions: "1",
          },
          invalid_session_count: "1",
        },
        operator_actions: {
          open_count: "19.8",
          total_actions: "20",
          closeable_count: "1",
          source_path: " docs/OPERATOR_ACTIONS.md ",
          next_action: {
            action_id: " OA-001 ",
            title: " Counsel review ",
            status_raw: " OPEN ",
            blocks: " payouts ",
            owner: " Legal ",
          },
          closeable_action: {
            action_id: " OA-005 ",
            title: " Wedge ratification ",
            status_raw: " AWAITING OPERATOR TEST ",
            blocks: " Phase 8 enforcing ",
            owner: " Operator ",
          },
        },
        engineering_deferrals: {
          open_count: "16.9",
          total_deferrals: "19",
          first_open: {
            deferral_id: " D1 ",
            title: " Multi-user pivot ",
            unlock_criterion: " G7 closes ",
          },
        },
        loop3: {
          manual_met_count: "1",
          evidence_passed_count: "0",
          total_criteria: "5",
          env_unlocked: "yes",
          fully_unlocked: "yes",
          first_failing_evidence: {
            criterion: " trajectory_volume ",
            evidence_summary: " events dir missing ",
          },
        },
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
    expect(screen.getByText("2")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /NaN|Infinity|\$-|-4|Skipped Publisher|leaky stats warning|object Object/,
    );
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
    expect(screen.getByText("$2.50")).toBeTruthy();
    expect(screen.getByText("1,500")).toBeTruthy();
    expect(screen.getByText("Coordination focus")).toBeTruthy();
    expect(screen.getByText("G2 · Counsel review")).toBeTruthy();
    expect(screen.getByText("OPEN · Legal")).toBeTruthy();
    expect(screen.getByText("Blocks: payouts")).toBeTruthy();
    expect(
      screen.getByText("Read dogfood 1/2 valid · 0 live-provider · 1 citation-traced"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Remaining: 9 valid, 5 live-provider, 2 citation-traced, 1 non-library. 1 invalid session need repair.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Operator actions 19/20 not closed · 1 awaiting operator test"),
    ).toBeTruthy();
    expect(
      screen.getByText("Closeable now: OA-005 · Wedge ratification. Blocks: Phase 8 enforcing."),
    ).toBeTruthy();
    expect(screen.getByText("Deferrals 16/19 not closed")).toBeTruthy();
    expect(
      screen.getByText("Do not pre-build D1 · Multi-user pivot. Unlock: G7 closes."),
    ).toBeTruthy();
    expect(
      screen.getByText("Loop 3 manual 1/5 · evidence 0/5 · env=locked"),
    ).toBeTruthy();
    expect(
      screen.getByText("First failing evidence: trajectory_volume · events dir missing."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "open →" }).getAttribute("href")).toBe(
      "/coordination",
    );
    expect(
      screen.getByRole("link", { name: "cost + consent →" }).getAttribute("href"),
    ).toBe("/coordination/cost-consent");
  });
});
