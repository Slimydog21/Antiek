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
    validated_reward: false,
    open_weight_justification: false,
    eval_headroom: false,
  },
  loop_3_evidence_status: {
    trajectory_volume: false,
    sft_readiness: false,
    validated_reward: false,
    open_weight_justification: false,
    eval_headroom: false,
  },
  loop_3_evidence_summaries: {
    trajectory_volume: "sealed_investigation_count: 0 >= 10000",
    eval_headroom: "eval_set_min_examples: 50 >= 200",
  },
  loop_3_all_evidence_passed: false,
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

const PREFERENCES_RESPONSE = {
  preferences: [
    {
      surface_name: "skill_invocation_frequency",
      epsilon_per_day: 2,
      sensitivity: "low",
      description: "Skill invocation frequency",
      opt_in_required: false,
      enabled: true,
      updated_at: "2026-07-01T06:00:00Z",
    },
    {
      surface_name: "source_tier_preference_signals",
      epsilon_per_day: 1,
      sensitivity: "medium",
      description: "Source tier preferences",
      opt_in_required: true,
      enabled: false,
      updated_at: "2026-07-01T06:00:00Z",
    },
    {
      surface_name: "query_content_telemetry",
      epsilon_per_day: 0,
      sensitivity: "forbidden",
      description: "Not collected",
      opt_in_required: false,
      enabled: false,
      updated_at: "2026-07-01T06:00:00Z",
    },
  ],
};

const TRUST_RESPONSE_WITH_DYNAMIC = {
  ...TRUST_RESPONSE,
  differential_privacy_epsilon_budgets: {
    ...TRUST_RESPONSE.differential_privacy_epsilon_budgets,
    dispatch_tier_telemetry: 0.5,
  },
};

const PREFERENCES_RESPONSE_WITH_DYNAMIC = {
  preferences: [
    ...PREFERENCES_RESPONSE.preferences,
    {
      surface_name: "dispatch_tier_telemetry",
      epsilon_per_day: 0.5,
      sensitivity: "high",
      description: "dispatch tier hint sampling",
      opt_in_required: true,
      enabled: false,
      updated_at: "2026-07-01T06:00:00Z",
    },
  ],
};

beforeEach(() => {
  apiFetchMock.mockReset().mockImplementation((path: string, init?: RequestInit) => {
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
    if (path === "/trust-center/telemetry-preferences") {
      return Promise.resolve({
        ok: true,
        json: async () => PREFERENCES_RESPONSE,
      });
    }
    if (
      path === "/trust-center/telemetry-preferences/skill_invocation_frequency" &&
      init?.method === "PATCH"
    ) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ...PREFERENCES_RESPONSE.preferences[0],
          enabled: false,
          updated_at: "2026-07-01T07:00:00Z",
        }),
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
    expect(screen.getByText("Noisy aggregate on")).toBeTruthy();
    expect(screen.getByText("Noisy aggregate off")).toBeTruthy();
    expect(screen.getByText("Encryption at rest with managed keys")).toBeTruthy();
    expect(
      screen.getByText("Access checks run before retrieved content is shown"),
    ).toBeTruthy();
    expect(screen.getByText("Future control")).toBeTruthy();
    expect(screen.getByText(/GDPR transparency notice/)).toBeTruthy();
    expect(
      screen.getByText(/Differential privacy with epsilon capped at 10/),
    ).toBeTruthy();
    expect(screen.getByText("Model training gate")).toBeTruthy();
    expect(screen.getByText("Evidence incomplete")).toBeTruthy();
    expect(screen.getByText("Operator checklist")).toBeTruthy();
    expect(screen.getByText("Evidence checks")).toBeTruthy();
    expect(screen.getAllByText("0/5")).toHaveLength(2);
    expect(screen.getByText("Trajectory volume")).toBeTruthy();
    expect(screen.getByText("SFT readiness")).toBeTruthy();
    expect(screen.getByText("Reward validation")).toBeTruthy();
    expect(screen.getByText("Open-weight rationale")).toBeTruthy();
    expect(screen.getByText("Evaluation headroom")).toBeTruthy();
    expect(screen.getAllByText("Not reviewed")).toHaveLength(5);
    expect(screen.getAllByText("Not verified")).toHaveLength(5);
    expect(screen.getByText(/Pending deletion request/)).toBeTruthy();
    expect(screen.getByText(/Deletion completes within 30 days/)).toBeTruthy();

    expect(screen.queryByText(/skill_invocation_frequency/i)).toBeNull();
    expect(screen.queryByText(/source_tier_preference_signals/i)).toBeNull();
    expect(screen.queryByText(/policy_tag/i)).toBeNull();
    expect(screen.queryByText(/future_control/i)).toBeNull();
    expect(screen.queryByText(/§/i)).toBeNull();
    expect(screen.queryByText(/substrate/i)).toBeNull();
    expect(screen.queryByText(/master-spec/i)).toBeNull();
    expect(screen.queryByText(/eval_set_min_examples/i)).toBeNull();
    expect(screen.queryByText(/sealed_investigation_count/i)).toBeNull();
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
        json: async () => PREFERENCES_RESPONSE,
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => PREFERENCES_RESPONSE,
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
        json: async () => PREFERENCES_RESPONSE,
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => PREFERENCES_RESPONSE,
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
      if (path === "/trust-center/telemetry-preferences") {
        return Promise.resolve({
          ok: true,
          json: async () => PREFERENCES_RESPONSE,
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

  it("shows a visible unavailable state when preference loading fails", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: true,
          json: async () => TRUST_RESPONSE,
        });
      }
      if (path === "/trust-center/deletion-requests") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ requests: [] }),
        });
      }
      return Promise.resolve({ ok: false, status: 503, json: async () => ({}) });
    });

    render(<PrivacyDashboard />);

    expect(
      await screen.findByText("Could not load privacy preferences; toggles unavailable."),
    ).toBeTruthy();
    expect(screen.getAllByText("Preference unavailable")).toHaveLength(2);
  });

  it("uses registry metadata for newly registered telemetry surfaces", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: true,
          json: async () => TRUST_RESPONSE_WITH_DYNAMIC,
        });
      }
      if (path === "/trust-center/deletion-requests") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ requests: [] }),
        });
      }
      if (path === "/trust-center/telemetry-preferences") {
        return Promise.resolve({
          ok: true,
          json: async () => PREFERENCES_RESPONSE_WITH_DYNAMIC,
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
    });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Dispatch tier hint sampling")).toBeTruthy();
    expect(screen.getByText("Sensitivity: High")).toBeTruthy();
    expect(screen.queryByText(/dispatch_tier_telemetry/i)).toBeNull();
  });

  it("sanitizes malformed epsilon budgets before rendering privacy promises", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...TRUST_RESPONSE,
            differential_privacy_epsilon_budgets: {
              skill_invocation_frequency: Number.NaN,
              source_tier_preference_signals: Number.POSITIVE_INFINITY,
              query_content_telemetry: -1,
              dispatch_tier_telemetry: 14,
            },
          }),
        });
      }
      if (path === "/trust-center/deletion-requests") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ requests: [] }),
        });
      }
      return Promise.resolve({ ok: false, status: 503, json: async () => ({}) });
    });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Daily privacy budget total: 10.00 of 10.00")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|Privacy budget: -/);
    expect(screen.getAllByText("Privacy budget: 0/day").length).toBeGreaterThan(0);
    expect(screen.getByText("Privacy budget: 10/day")).toBeTruthy();
  });

  it("sanitizes privacy dashboard API payloads before rendering", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/trust-center") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            differential_privacy_epsilon_budgets: {
              " dispatch_tier_telemetry ": "4.25",
              " ": 10,
              malformed_budget: "Infinity",
            },
            deletion_sla_days: "12.9",
            substrate_controls: [
              " encryption at rest (per-graph keys via KMS) ",
              "",
              42,
              "encryption at rest (per-graph keys via KMS)",
            ],
            compliance_frameworks: [
              " GDPR Article 13/14 transparency ",
              null,
              "GDPR Article 13/14 transparency",
            ],
            loop_3_unlock_status: {
              " trajectory_volume ": true,
              sft_readiness: "yes",
              " ": true,
            },
            loop_3_evidence_status: {
              " trajectory_volume ": true,
              eval_headroom: "yes",
            },
            loop_3_evidence_summaries: {
              " trajectory_volume ": " sealed_investigation_count: 10 ",
              " ": "Skipped summary",
            },
            loop_3_all_evidence_passed: "yes",
          }),
        });
      }
      if (path === "/trust-center/deletion-requests") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            requests: [
              {
                request_id: " del dirty ",
                status: " pending ",
                requested_at: " 2026-07-01T06:00:00Z ",
                cancellation_window_days: "7.9",
                deletion_sla_days: "12.9",
              },
              {
                request_id: " ",
                status: "pending",
                requested_at: "Skipped request",
              },
            ],
          }),
        });
      }
      if (path === "/trust-center/telemetry-preferences") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            preferences: [
              {
                surface_name: " dispatch_tier_telemetry ",
                epsilon_per_day: "4.25",
                sensitivity: "medium",
                description: " query snippets ",
                opt_in_required: "yes",
                enabled: "yes",
                updated_at: " ",
              },
              {
                surface_name: " ",
                description: "Skipped preference",
              },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
    });

    render(<PrivacyDashboard />);

    expect(await screen.findByText("Query snippets")).toBeTruthy();
    expect(screen.getByText("Daily privacy budget total: 4.25 of 10.00")).toBeTruthy();
    expect(screen.getByText("Privacy budget: 4.25/day")).toBeTruthy();
    expect(screen.getByText("Sensitivity: Medium")).toBeTruthy();
    expect(screen.getByText("Noisy aggregate off")).toBeTruthy();
    expect(screen.getByText("Encryption at rest with managed keys")).toBeTruthy();
    expect(screen.getByText(/GDPR transparency notice/)).toBeTruthy();
    expect(screen.getAllByText("1/5")).toHaveLength(2);
    expect(screen.getByText(/Pending deletion request/)).toBeTruthy();
    expect(screen.getByText(/Cancellation window: 7 days/)).toBeTruthy();
    expect(screen.getByText(/Deletion completes within 12 days/)).toBeTruthy();

    expect(document.body.textContent).not.toMatch(
      /Skipped|NaN|Infinity|Privacy budget: -|del dirty|request_id|sealed_investigation_count/,
    );
  });

  it("updates a telemetry preference through the privacy toggle", async () => {
    render(<PrivacyDashboard />);

    expect(await screen.findByText("Skill Use Frequency")).toBeTruthy();
    const aggregateOn = screen.getByLabelText(/Noisy aggregate on/i);
    await userEvent.click(aggregateOn);

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/trust-center/telemetry-preferences/skill_invocation_frequency",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ enabled: false }),
      }),
    );
    expect(await screen.findAllByText("Noisy aggregate off")).toHaveLength(2);
  });
});
