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
    if (path === "/trust-center") {
      return okJson({
        differential_privacy_epsilon_budgets: {
          skill_invocation_frequency: "2",
          source_tier_preference_signals: Number.NaN,
          query_content_telemetry: "0.5",
          " ": 9,
        },
        deletion_sla_days: "30.9",
        substrate_controls: [" encryption at rest ", "", 42, " policy gating "],
        compliance_frameworks: [" GDPR ", null],
        loop_3_evidence_status: {
          trajectory_volume: true,
          sft_readiness: "yes",
          validated_reward: false,
        },
        loop_3_all_evidence_passed: "true",
      });
    }
    if (path.startsWith("/billing/summary/__operator__/")) {
      return okJson({
        period: " 2026-07 ",
        free_tokens_consumed: "1234.9",
        free_tokens_remaining: "4998765.1",
        total_margin_usd: "0.025",
        total_billable_usd: "0.275",
        record_count: "2.9",
      });
    }
    if (path === "/investigations?limit=200") {
      return okJson({
        investigations: [
          {
            investigation_id: " inv-a ",
            status: " in_progress ",
            cost_usd_total: "0.0125",
          },
          {
            investigation_id: "inv-b",
            status: "completed",
            cost_usd_total: Number.NaN,
          },
          {
            investigation_id: "inv-c",
            status: "failed",
            cost_usd_total: "0.0075",
          },
          {
            investigation_id: " ",
            status: "failed",
            cost_usd_total: "999",
          },
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
        source_gate: {
          state: " blocked ",
          source_count: "1",
          blocked_count: "1",
          reference_source: " arxiv ",
          rows: [
            {
              source: " web ",
              blocked: true,
              failures: [" metadata_complete_pct=94.0 < 95.0 "],
            },
          ],
          error: " ",
        },
      });
    }
    if (path === "/marketplace/snapshot") {
      return okJson({
        health: "unknown",
        health_signals: [" publisher claims need work ", "", 42],
        creators: {
          creator_count: "2.9",
          total_paid_cents: "2500",
        },
        publishers: {
          status_counts: {
            claim_rate: "0.125",
          },
          total_escrow_accrued_cents: Number.POSITIVE_INFINITY,
          unclaimed_escrow_cents: Number.NaN,
        },
        advertisers: {
          advertiser_count_current: "4",
          retention_rate: Number.NaN,
          total_spend_current_cents: "9876",
          crosses_self_service_threshold: "yes",
        },
      });
    }
    if (path === "/federation/config") {
      return okJson({
        allowed_partner_substrates: [
          " partner-a ",
          "partner-a",
          "",
          42,
          "partner-b",
        ],
        require_opt_in_for_outbound_citations: "false",
        require_attribution_for_outbound_citations: false,
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
    expect(screen.getByText("Source gate blocked · 1/1 blocked")).toBeTruthy();
    expect(
      screen.getByText("web: metadata_complete_pct=94.0 < 95.0"),
    ).toBeTruthy();
    expect(screen.getByText("Marketplace health")).toBeTruthy();
    expect(screen.getByText("WATCH · 2 creators · 4 advertisers")).toBeTruthy();
    expect(
      screen.getByText("Paid $25.00 · escrow $0.00 · ad spend $98.76."),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Publisher claims 12.5% · advertiser retention 0.0% · self-service not crossed.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Signal: publisher claims need work.")).toBeTruthy();
    expect(screen.getByText("Privacy controls")).toBeTruthy();
    expect(
      screen.getByText("Privacy budget 2.50/10.00 · deletion SLA 30 days"),
    ).toBeTruthy();
    expect(screen.getByText("2 controls · 1 frameworks.")).toBeTruthy();
    expect(
      screen.getByText("Training evidence 1/3 · evidence incomplete."),
    ).toBeTruthy();
    expect(screen.getByText("Research workload")).toBeTruthy();
    expect(
      screen.getByText("3 visible · 1 in progress · 1 completed · 1 failed"),
    ).toBeTruthy();
    expect(screen.getByText("Visible research cost $0.0200.")).toBeTruthy();
    expect(screen.getByText("Billing usage")).toBeTruthy();
    expect(
      screen.getByText("2026-07 · billable $0.2750 · margin $0.0250"),
    ).toBeTruthy();
    expect(
      screen.getByText("Free tier 1,234 consumed · 4,998,765 remaining."),
    ).toBeTruthy();
    expect(screen.getByText("2 usage records aggregated.")).toBeTruthy();
    expect(screen.getByText("Federation status")).toBeTruthy();
    expect(screen.getByText("CONFIGURED · 2 partners")).toBeTruthy();
    expect(
      screen.getByText("Outbound citations require opt-in: yes · attribution: no."),
    ).toBeTruthy();
    expect(screen.getByText("Partners: partner-a, partner-b.")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /partner-a\s+partner-a|42/,
    );
    const openLinks = screen
      .getAllByRole("link", { name: "open →" })
      .map((link) => link.getAttribute("href"));
    expect(openLinks).toContain("/coordination");
    expect(openLinks).toContain("/investigations");
    expect(openLinks).toContain("/billing");
    expect(openLinks).toContain("/privacy");
    expect(openLinks).toContain("/marketplace");
    expect(openLinks).toContain("/federation");
    expect(
      screen.getByRole("link", { name: "cost + consent →" }).getAttribute("href"),
    ).toBe("/coordination/cost-consent");
  });
});
