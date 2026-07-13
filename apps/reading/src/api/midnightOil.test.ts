import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  approveMidnightOilCeiling,
  canRetryMidnightOilAdmission,
  createMidnightOilJob,
  describeMidnightOilAdmission,
  getMidnightOilJob,
  retryMidnightOilGraphAdmission,
  runMidnightOilJob,
} from "./midnightOil";

const mockFetch = vi.fn();

const V1_POLICY = {
  policy_version: 1 as const,
  required_coverage: "insights_and_output_paragraphs" as const,
  exploratory_questions: "operational_only" as const,
  external_receipts: "local_canonical_chunk_required" as const,
  unsupported_output: "retain_operational_only" as const,
  legacy_rows: "legacy_unverified" as const,
};

const V1_LAUNCH = {
  acceptance_policy_version: 1 as const,
  acceptance_policy: V1_POLICY,
  research_brief_state: "approved" as const,
  research_brief_hash: "a".repeat(64),
  approved_research_brief_hash: "a".repeat(64),
};

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => mockFetch(...args),
}));

describe("midnightOil API client", () => {
  beforeEach(() => mockFetch.mockReset());

  it("createMidnightOilJob posts goals + duration", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        acceptance_policy_version: 1,
        acceptance_policy: V1_POLICY,
        recommended_price_ceiling_usd: 3.6,
        graph_node_ids: ["node-ok", ""],
        graph_deliverable_id: 42,
        view_format: "html",
        runnable: false,
      }),
    });
    const out = await createMidnightOilJob({
      goals: ["g"],
      duration_minutes: 60,
    });
    expect(out.recommended_price_ceiling_usd).toBe(3.6);
    expect(out.view_format).toBe("html");
    expect(out.graph_node_ids).toEqual([]);
    expect(out.graph_deliverable_id).toBeNull();
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/create",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("approveMidnightOilCeiling posts use_recommended", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        acceptance_policy_version: 1,
        acceptance_policy: V1_POLICY,
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "signed-consent-token",
        operation_id: "operation-1",
        ceiling_cents: 360,
        issued_at_ms: 100,
        expires_at_ms: Date.now() + 60_000,
      }),
    });
    const out = await approveMidnightOilCeiling({
      job_id: "moil_1",
      use_recommended: true,
    });
    expect(out.runnable).toBe(true);
    expect(out.status).toBe("approved");
    expect(out.approved_ceiling_usd).toBe(3.6);
    expect(mockFetch.mock.calls[1][0]).toBe(
      "/midnight-oil/jobs/moil_1/spend-consent",
    );
    expect(JSON.parse(mockFetch.mock.calls[1][1].body)).toEqual({
      ceiling_cents: null,
      use_recommended: true,
      force_below: false,
      acceptance_policy_version: 1,
    });
  });

  it.each([
    [
      "no_result",
      { graph_projection_state: "pending", research_result_state: "none" },
    ],
    [
      "receipt_only",
      { graph_projection_state: "pending", research_result_state: "receipt_only" },
    ],
    ["admitted", { graph_projection_state: "complete" }],
    [
      "refused",
      {
        graph_projection_state: "refused",
        graph_projection_reason: "legacy_unverified",
      },
    ],
    [
      "reconciliation_required",
      {
        graph_projection_state: "refused",
        graph_projection_reason: "policy_authority_drift",
      },
    ],
    ["unknown", { graph_projection_state: "future_state" }],
    [
      "unknown",
      {
        graph_projection_state: "future_state",
        graph_projection_reason: "policy_authority_drift",
      },
    ],
    ["unknown", { graph_projection_state: "refused" }],
    [
      "unknown",
      {
        graph_projection_state: "refused",
        graph_projection_reason: "graph_lock_unavailable",
      },
    ],
    [
      "unknown",
      {
        graph_projection_state: "pending",
        graph_projection_reason: "claim_coverage_missing",
      },
    ],
    [
      "not_started",
      {
        status: "consent_issued",
        graph_projection_state: "pending",
        research_result_state: "none",
      },
    ],
    [
      "unknown",
      {
        graph_projection_state: "complete",
        graph_projection_reason: "future_reason",
      },
    ],
    [
      "reconciliation_required",
      {
        graph_projection_state: "complete",
        research_brief_hash: "a".repeat(64),
        approved_research_brief_hash: "b".repeat(64),
      },
    ],
    [
      "unknown",
      {
        graph_projection_state: "complete",
        graph_projection_reason: "claim_coverage_missing",
      },
    ],
  ])("maps graph admission to honest %s copy", (expected, job) => {
    const presentation = describeMidnightOilAdmission({ ...V1_LAUNCH, ...job });
    expect(presentation.state).toBe(expected);
    expect(presentation.verified).toBe(expected === "admitted");
  });

  it.each([
    "internal_local_chunk_temporarily_missing",
    "operational_artifact_pending",
    "graph_lock_unavailable",
  ])("permits operator retry only for terminal transient reason %s", (reason) => {
    expect(
      canRetryMidnightOilAdmission({
        ...V1_LAUNCH,
        status: "complete",
        research_result_state: "returned",
        deposit_state: "complete",
        graph_projection_state: "pending",
        graph_projection_reason: reason,
      }),
    ).toBe(true);
  });

  it.each([
    "policy_authority_drift",
    "legacy_unverified",
    "claim_coverage_missing",
    "receipt_malformed_or_forged",
    "external_receipt_not_admissible_v1",
    "deterministic_row_conflict",
    null,
  ])("refuses operator retry for non-transient reason %s", (reason) => {
    expect(
      canRetryMidnightOilAdmission({
        ...V1_LAUNCH,
        status: "complete",
        research_result_state: "returned",
        deposit_state: "complete",
        graph_projection_state: reason ? "refused" : "pending",
        graph_projection_reason: reason,
      }),
    ).toBe(false);
  });

  it("fails closed when version 1 is paired with an incomplete policy", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "moil_policy_drift",
        status: "awaiting_approval",
        acceptance_policy_version: 1,
        acceptance_policy: { policy_version: 1 },
      }),
    });

    await expect(
      approveMidnightOilCeiling({
        job_id: "moil_policy_drift",
        use_recommended: true,
      }),
    ).rejects.toThrow(/exact v1 research acceptance policy/i);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("converts custom USD to integer cents and queues with in-memory consent", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "moil_custom",
          goals: ["g1", "g2"],
          duration_minutes: 60,
          status: "awaiting_approval",
          acceptance_policy_version: 1,
          acceptance_policy: V1_POLICY,
          recommended_price_ceiling_usd: 3.6,
          view_format: "html",
          runnable: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: "secret-consent",
          operation_id: "operation-custom",
          ceiling_cents: 425,
          issued_at_ms: 100,
          expires_at_ms: Date.now() + 60_000,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "moil_custom",
          operation_id: "operation-custom",
          state: "queued",
          graph_node_ids: ["node-live"],
          graph_deliverable_id: "deliverable-live",
        }),
      });

    await approveMidnightOilCeiling({
      job_id: "moil_custom",
      ceiling_usd: 4.25,
      force_below: true,
    });
    const queued = await runMidnightOilJob({
      job_id: "moil_custom",
      auto_deposit: true,
    });

    expect(JSON.parse(mockFetch.mock.calls[1][1].body)).toEqual({
      ceiling_cents: 425,
      use_recommended: false,
      force_below: true,
      acceptance_policy_version: 1,
    });
    expect(mockFetch.mock.calls[2][1].headers).toEqual(
      expect.objectContaining({
        "X-Midnight-Oil-Spend-Consent": "secret-consent",
      }),
    );
    expect(JSON.parse(mockFetch.mock.calls[2][1].body)).toEqual(
      expect.objectContaining({
        job_id: "moil_custom",
        auto_deposit: true,
        force_offline: true,
      }),
    );
    expect(queued).toEqual(
      expect.objectContaining({
        queued: true,
        queue_state: "queued",
        operation_id: "operation-custom",
        status: "queued",
        spent_usd: 0,
        spawn_ids: [],
        graph_node_ids: ["node-live"],
        graph_deliverable_id: "deliverable-live",
      }),
    );
    expect(JSON.stringify(queued)).not.toContain("secret-consent");
    expect(mockFetch.mock.calls[2][0]).not.toContain("secret-consent");
    expect(mockFetch.mock.calls[2][1].body).not.toContain("secret-consent");
    await expect(
      runMidnightOilJob({ job_id: "moil_custom" }),
    ).rejects.toThrow(/fresh in-memory spend consent/);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("rejects sub-cent custom authority before issuing consent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "moil_fractional",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        acceptance_policy_version: 1,
        acceptance_policy: V1_POLICY,
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
    });
    await expect(
      approveMidnightOilCeiling({
        job_id: "moil_fractional",
        ceiling_usd: 1.001,
      }),
    ).rejects.toThrow(/two decimal places/);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("rejects sub-cent values even inside the former float tolerance", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "moil_tiny_fraction",
        goals: ["g"],
        duration_minutes: 60,
        status: "awaiting_approval",
        acceptance_policy_version: 1,
        acceptance_policy: V1_POLICY,
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
      }),
    });
    await expect(
      approveMidnightOilCeiling({
        job_id: "moil_tiny_fraction",
        ceiling_usd: 1.0000000005,
      }),
    ).rejects.toThrow(/two decimal places/);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("discards definitively rejected consent so the job can be reapproved", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "moil_expired",
          goals: ["g"],
          duration_minutes: 60,
          status: "awaiting_approval",
          acceptance_policy_version: 1,
          acceptance_policy: V1_POLICY,
          recommended_price_ceiling_usd: 3.6,
          view_format: "html",
          runnable: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: "expired-on-server",
          operation_id: "operation-expired",
          ceiling_cents: 360,
          issued_at_ms: Date.now() - 1_000,
          expires_at_ms: Date.now() + 60_000,
        }),
      })
      .mockResolvedValueOnce({ ok: false, status: 403 });
    await approveMidnightOilCeiling({
      job_id: "moil_expired",
      use_recommended: true,
    });
    await expect(
      runMidnightOilJob({ job_id: "moil_expired" }),
    ).rejects.toThrow(/expired; approve again/);
    await expect(
      runMidnightOilJob({ job_id: "moil_expired" }),
    ).rejects.toThrow(/fresh in-memory spend consent/);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("discards consent after a definitive non-403 client rejection", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "moil_conflict",
          goals: ["g"],
          duration_minutes: 60,
          status: "awaiting_approval",
          acceptance_policy_version: 1,
          acceptance_policy: V1_POLICY,
          recommended_price_ceiling_usd: 3.6,
          view_format: "html",
          runnable: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: "conflicted-consent",
          operation_id: "operation-conflict",
          ceiling_cents: 360,
          issued_at_ms: Date.now() - 1_000,
          expires_at_ms: Date.now() + 60_000,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        text: async () => "operation replay options conflict",
      });
    await approveMidnightOilCeiling({
      job_id: "moil_conflict",
      use_recommended: true,
    });
    await expect(
      runMidnightOilJob({ job_id: "moil_conflict" }),
    ).rejects.toThrow(/API 409/);
    await expect(
      runMidnightOilJob({ job_id: "moil_conflict" }),
    ).rejects.toThrow(/fresh in-memory spend consent/);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("getMidnightOilJob fetches by id", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil_1",
        goals: ["g"],
        duration_minutes: 60,
        status: "approved",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: true,
      }),
    });
    const out = await getMidnightOilJob("moil_1");
    expect(out.job_id).toBe("moil_1");
    expect(out.graph_node_ids).toEqual([]);
    expect(out.graph_deliverable_id).toBeNull();
    expect(mockFetch.mock.calls[0][0]).toBe("/midnight-oil/jobs/moil_1");
  });

  it("retries graph admission with an empty POST and normalizes navigation", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "moil/retry",
        goals: ["g"],
        duration_minutes: 60,
        status: "complete",
        recommended_price_ceiling_usd: 3.6,
        view_format: "html",
        runnable: false,
        graph_projection_state: "complete",
        graph_node_ids: ["node-1"],
        graph_deliverable_id: "dlv-1",
      }),
    });
    const out = await retryMidnightOilGraphAdmission("moil/retry");
    expect(out.graph_projection_state).toBe("complete");
    expect(out.graph_node_ids).toEqual(["node-1"]);
    expect(mockFetch).toHaveBeenCalledWith(
      "/midnight-oil/jobs/moil%2Fretry/graph-admission/retry",
      { method: "POST" },
    );
  });
});
