import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PrivacyDashboard from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

const TRUST_RESPONSE = {
  differential_privacy_epsilon_budgets: {
    skill_invocation_frequency: 2,
    source_tier_preference_signals: 1,
    query_content_telemetry: 0,
  },
  deletion_sla_days: 30,
  substrate_controls: [
    "encryption at rest (per-graph keys via KMS)",
    "retrieval-time policy_tag gating (§9.0)",
    "future_control (§7.4)",
  ],
  compliance_frameworks: [
    "GDPR Article 13/14 transparency",
    "engineering-grade differential privacy (ε ≤ 10 hard cap)",
  ],
  loop_3_unlock_status: {
    trajectory_volume: false,
    sft_readiness: false,
  },
};

const DELETION_RESPONSE = {
  requests: [
    {
      request_id: "del-raw-123",
      status: "pending",
      requested_at: "2026-07-01T06:00:00Z",
      cancellation_window_days: 7,
      deletion_sla_days: 30,
    },
  ],
};

beforeEach(() => {
  apiFetchMock.mockReset().mockImplementation((path: string) => {
    if (path === "/trust-center") {
      return Promise.resolve({
        ok: true,
        json: async () => TRUST_RESPONSE,
      });
    }
    if (path === "/trust-center/deletion-requests") {
      return Promise.resolve({
        ok: true,
        json: async () => DELETION_RESPONSE,
      });
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
  });
});

afterEach(() => {
  cleanup();
});

describe("PrivacyDashboard", () => {
  it("renders privacy data without leaking trust-center internals", async () => {
    render(<PrivacyDashboard />);

    expect(await screen.findByText("Skill Use Frequency")).toBeTruthy();
    expect(screen.getByText("Source Preference Signals")).toBeTruthy();
    expect(screen.getByText("Search Content Telemetry")).toBeTruthy();
    expect(screen.getByText("Daily privacy budget total: 3.00 of 10.00")).toBeTruthy();
    expect(screen.getByText("Privacy budget: 2/day")).toBeTruthy();
    expect(screen.getByText("Never collected")).toBeTruthy();
    expect(screen.getByText("Sensitivity: Low")).toBeTruthy();
    expect(screen.getByText("Sensitivity: Medium")).toBeTruthy();
    expect(screen.getByText("Sensitivity: Not collected")).toBeTruthy();
    expect(screen.getByText("Encryption at rest with managed keys")).toBeTruthy();
    expect(
      screen.getByText("Access checks run before retrieved content is shown"),
    ).toBeTruthy();
    expect(screen.getByText("Future control")).toBeTruthy();
    expect(screen.getByText(/GDPR transparency notice/)).toBeTruthy();
    expect(
      screen.getByText(/Differential privacy with epsilon capped at 10/),
    ).toBeTruthy();
    expect(screen.getByText(/Pending deletion request/)).toBeTruthy();
    expect(screen.getByText(/Deletion completes within 30 days/)).toBeTruthy();

    expect(screen.queryByText(/skill_invocation_frequency/i)).toBeNull();
    expect(screen.queryByText(/source_tier_preference_signals/i)).toBeNull();
    expect(screen.queryByText(/policy_tag/i)).toBeNull();
    expect(screen.queryByText(/future_control/i)).toBeNull();
    expect(screen.queryByText(/§/i)).toBeNull();
    expect(screen.queryByText(/substrate/i)).toBeNull();
    expect(screen.queryByText(/master-spec/i)).toBeNull();
    expect(screen.queryByText(/request_id/i)).toBeNull();
    expect(screen.queryByText(/del-raw-123/i)).toBeNull();
    expect(screen.queryByText(/GET \/trust-center/i)).toBeNull();
  });

  it("shows a friendly privacy load error", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: async () => ({}),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ requests: [] }) });
    });

    render(<PrivacyDashboard />);

    expect(
      await screen.findByText("Could not load privacy settings (HTTP 503)."),
    ).toBeTruthy();
    expect(screen.queryByText(/GET \/trust-center failed/i)).toBeNull();
  });

  it("clears a cancelled deletion request even if the refresh fails", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => TRUST_RESPONSE,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => DELETION_RESPONSE,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ requests: [] }),
      });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Skill Use Frequency")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel deletion request" }));

    expect(
      await screen.findByText("Could not load privacy settings (HTTP 503)."),
    ).toBeTruthy();
    expect(screen.getByText("Skill Use Frequency")).toBeTruthy();
    expect(screen.queryByText(/Pending deletion request/)).toBeNull();
  });

  it("keeps the created deletion request visible if refresh after request fails", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => TRUST_RESPONSE,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ requests: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          request_id: "del-created-1",
          status: "pending",
          requested_at: "2026-07-01T07:00:00Z",
          cancellation_window_days: 7,
          deletion_sla_days: 30,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ requests: [] }),
      });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Skill Use Frequency")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Request deletion" }));

    expect(
      await screen.findByText("Could not load privacy settings (HTTP 503)."),
    ).toBeTruthy();
    expect(screen.getByText(/Pending deletion request/)).toBeTruthy();
    expect(screen.queryByText(/del-created-1/)).toBeNull();
  });

  it("does not offer a new deletion request when deletion status is unavailable", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: true,
          json: async () => TRUST_RESPONSE,
        });
      }
      return Promise.resolve({ ok: false, status: 503, json: async () => ({}) });
    });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Skill Use Frequency")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Deletion status unavailable" }),
    ).toHaveProperty("disabled", true);
  });
});
