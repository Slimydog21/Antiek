import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import TrustCenter from "./index";

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
  ],
  compliance_frameworks: [
    "GDPR Article 13/14 transparency",
    "engineering-grade differential privacy (ε ≤ 10 hard cap)",
  ],
  loop_3_unlock_status: {
    trajectory_volume: false,
    sft_readiness: true,
    validated_reward: false,
  },
};

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({
    ok: true,
    json: async () => TRUST_RESPONSE,
  });
});

afterEach(() => {
  cleanup();
});

describe("TrustCenter", () => {
  it("renders live trust data with user-facing labels", async () => {
    render(<TrustCenter />);

    expect(await screen.findByText("Privacy budget")).toBeTruthy();
    expect(screen.getByText("Deletion window")).toBeTruthy();
    expect(screen.getByText("System controls")).toBeTruthy();
    expect(screen.getByText("Training controls")).toBeTruthy();
    expect(screen.getByText("Compliance posture")).toBeTruthy();

    expect(apiFetchMock).toHaveBeenCalledWith("/trust-center");
    expect(screen.getByText("Skill Use Frequency")).toBeTruthy();
    expect(screen.getByText("Source Preference Signals")).toBeTruthy();
    expect(screen.getByText("Search Content Telemetry")).toBeTruthy();
    expect(screen.getByText("epsilon is always 10 or lower.", { exact: false })).toBeTruthy();
    expect(screen.getByText(/completed within 30 days/)).toBeTruthy();
    expect(screen.getByText("Encryption at rest with managed keys")).toBeTruthy();
    expect(
      screen.getByText("Access checks run before retrieved content is shown"),
    ).toBeTruthy();
    expect(screen.getByText("GDPR transparency notice")).toBeTruthy();
    expect(
      screen.getByText("Differential privacy with epsilon capped at 10"),
    ).toBeTruthy();
    expect(screen.getByText("Enough approved activity")).toBeTruthy();
    expect(screen.getByText("Training data quality review")).toBeTruthy();
    expect(screen.getAllByText("Not met")).toHaveLength(2);
    expect(screen.getByText("Met")).toBeTruthy();

    expect(screen.queryByText(/skill_invocation_frequency/i)).toBeNull();
    expect(screen.queryByText(/source_tier_preference_signals/i)).toBeNull();
    expect(screen.queryByText(/policy_tag/i)).toBeNull();
    expect(screen.queryByText(/§/i)).toBeNull();
    expect(screen.queryByText(/sft_readiness/i)).toBeNull();
    expect(screen.queryByText(/trajectory_volume/i)).toBeNull();
    expect(screen.queryByText(/master-spec/i)).toBeNull();
    expect(screen.queryByText(/ANTIEK_LOOP3_UNLOCKED/i)).toBeNull();
    expect(screen.queryByText(/substrate/i)).toBeNull();
    expect(screen.queryByText(/operator/i)).toBeNull();
    expect(screen.queryByText(/GET \/trust-center/i)).toBeNull();
  });

  it("shows a friendly load error instead of the raw request label", async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    });

    render(<TrustCenter />);

    expect(
      await screen.findByText("Could not load the Trust Center (HTTP 503)."),
    ).toBeTruthy();
    expect(screen.queryByText(/GET \/trust-center failed/i)).toBeNull();
  });

  it("sanitizes malformed epsilon values before rendering the public cap", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...TRUST_RESPONSE,
        differential_privacy_epsilon_budgets: {
          skill_invocation_frequency: Number.NaN,
          source_tier_preference_signals: Number.POSITIVE_INFINITY,
          query_content_telemetry: -1,
          dispatch_tier_telemetry: 14.25,
        },
      }),
    });

    render(<TrustCenter />);

    expect(await screen.findByText("Privacy budget")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|Epsilon: -/);
    expect(screen.getAllByText("Epsilon: 0").length).toBeGreaterThan(0);
    expect(screen.getByText("Epsilon: 10")).toBeTruthy();
  });

  it("sanitizes malformed trust payload shape before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        differential_privacy_epsilon_budgets: {
          " query_content_telemetry ": "4.25",
          " ": 9,
          malformed_category: "Infinity",
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
      }),
    });

    render(<TrustCenter />);

    expect(await screen.findByText("Privacy budget")).toBeTruthy();
    expect(screen.getByText("Search Content Telemetry")).toBeTruthy();
    expect(screen.getByText("Epsilon: 4.25")).toBeTruthy();
    expect(screen.getByText("Epsilon: 0")).toBeTruthy();
    expect(screen.getByText(/completed within 12 days/)).toBeTruthy();
    expect(screen.getByText("Encryption at rest with managed keys")).toBeTruthy();
    expect(screen.getByText("GDPR transparency notice")).toBeTruthy();
    expect(screen.getAllByText("Encryption at rest with managed keys")).toHaveLength(1);
    expect(screen.getAllByText("GDPR transparency notice")).toHaveLength(1);
    expect(screen.getByText("Enough approved activity")).toBeTruthy();
    expect(screen.getByText("Training data quality review")).toBeTruthy();
    expect(screen.getByText("Met")).toBeTruthy();
    expect(screen.getByText("Not met")).toBeTruthy();

    expect(document.body.textContent).not.toMatch(/NaN|Infinity|Epsilon: -/);
    expect(screen.queryByText(/undefined|null|42/)).toBeNull();
  });
});
