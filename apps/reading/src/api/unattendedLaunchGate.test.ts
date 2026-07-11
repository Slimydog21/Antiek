import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  LaunchGateHttpError,
  formatLaunchGateSummary,
  parseLaunchGateDecision,
  postUnattendedLaunchGate,
} from "./unattendedLaunchGate";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  dispatch_ready: true,
  live_execution_authorized: false,
  zero_ceiling_dry_run: false,
  operator_approved: true,
  consent_receipt_id: "rcpt-1",
  brief: {
    duration_minutes: 90,
    goals: ["map X"],
    approved_ceiling_cents: 200,
    recommended_ceiling_cents: null,
    notes: [],
    live_execution_authorized: false,
    authority: "operator_brief_only",
  },
  reasons: [],
  notes: ["live_execution_authorized=false"],
  authority: "launch_gate_advisory",
};

describe("parseLaunchGateDecision", () => {
  it("parses ready decision", () => {
    const d = parseLaunchGateDecision(sample);
    expect(d.dispatch_ready).toBe(true);
    expect(d.live_execution_authorized).toBe(false);
  });

  it("rejects live true", () => {
    expect(() =>
      parseLaunchGateDecision({ ...sample, live_execution_authorized: true }),
    ).toThrow(/live_execution_authorized/);
  });

  it("rejects dispatch_ready without receipt when ceiling>0", () => {
    expect(() =>
      parseLaunchGateDecision({
        ...sample,
        consent_receipt_id: null,
        brief: { ...sample.brief, approved_ceiling_cents: 50 },
      }),
    ).toThrow(/consent_receipt_id/);
  });
});

describe("postUnattendedLaunchGate", () => {
  it("POSTs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const d = await postUnattendedLaunchGate({
      operator_approved: true,
      consent_receipt_id: "rcpt-1",
      duration_minutes: 90,
      goals: ["map X"],
      approved_ceiling_cents: 200,
    });
    expect(d.authority).toBe("launch_gate_advisory");
  });

  it("rejects missing operator_approved without network", async () => {
    await expect(
      postUnattendedLaunchGate({
        operator_approved: undefined as unknown as boolean,
        duration_minutes: 30,
        goals: ["x"],
        approved_ceiling_cents: 0,
      }),
    ).rejects.toThrow(/operator_approved/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postUnattendedLaunchGate({
        operator_approved: true,
        duration_minutes: 30,
        goals: ["x"],
        approved_ceiling_cents: 0,
      }),
    ).rejects.toBeInstanceOf(LaunchGateHttpError);
  });
});

describe("formatLaunchGateSummary", () => {
  it("summarizes", () => {
    expect(formatLaunchGateSummary(parseLaunchGateDecision(sample))).toMatch(
      /dispatch_ready=true/,
    );
  });
});
