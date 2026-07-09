/**
 * Tests for the multimedia API client (SPR-09 + SPR-11).
 *
 * `fetch` is mocked (no network). Covers the create/list/get/approve/steer/
 * harden surface and the SPR-11 jobs endpoint: listMultimediaJobs resolves
 * ordered job rows, the response type carries latest job status, and a 404
 * surfaces the typed not-found error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  approveMultimediaDryRun,
  createMultimediaDraft,
  evaluateMultimediaPublicExportGate,
  failedGateIds,
  getMultimediaAsset,
  getMultimediaPublicExportStatus,
  listMultimediaAssets,
  listMultimediaJobs,
  manualGateIds,
  planMultimediaPublicExport,
  prepareMultimediaLiveExecution,
  recordMultimediaPublicExportReview,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "./multimedia";
import type { MultimediaAssetRecord, MultimediaPublicExportStatus } from "./multimedia";

const record: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    status: "ready",
    kind: "documentary_video",
    title: "widebody economics",
    route_policy: "cheapest",
    requested_duration_minutes: 20,
    parent_revision_id: null,
    steering_event_id: null,
    manifest: { cost_rows: [{ cost_usd: 0 }] },
  },
  plan: { chapters: [] },
  mode: "hybrid",
  style: null,
  hardening_report: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    ship_status: "manual_review",
    gates: [
      { gate_id: "rights_and_publication", status: "manual", findings: [] },
      { gate_id: "budget", status: "fail", findings: [] },
    ],
    residual_risks: [],
  },
  latest_steering_intent: null,
  jobs: [
    {
      job_id: "job-mm-1-0001",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 1,
      kind: "render",
      status: "succeeded",
      progress_percent: 100,
      message: "Dry-run render manifest assembled without live provider spend.",
      error_code: null,
      retryable: null,
    },
  ],
};

const exportGateRecord: MultimediaAssetRecord = {
  ...record,
  jobs: [
    ...record.jobs,
    {
      job_id: "job-mm-1-0002",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 2,
      kind: "export_gate",
      status: "partial",
      progress_percent: 95,
      message: "Manual publication review required before public export.",
      error_code: null,
      retryable: true,
      public_export_gate: {
        status: "manual_review",
        public_export_enabled: false,
        hardening_status: "manual_review",
        attached_file_ids: ["file-mm-1-transcript"],
        required_gate_ids: ["rights_and_publication"],
        reason: "Manual publication review required before public export.",
      },
    },
  ],
};

const exportReviewRecord: MultimediaAssetRecord = {
  ...record,
  jobs: [
    ...exportGateRecord.jobs,
    {
      job_id: "job-mm-1-0003",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 3,
      kind: "export_gate",
      status: "partial",
      progress_percent: 98,
      message: "Manual publication review approved; public export remains disabled.",
      error_code: null,
      retryable: false,
      public_export_gate: {
        status: "ready",
        public_export_enabled: false,
        hardening_status: "manual_review",
        attached_file_ids: ["file-mm-1-transcript"],
        required_gate_ids: [],
        reason: "Manual publication review approved; public export remains disabled.",
      },
      public_export_review: {
        decision: "approved",
        gate_ids: ["rights_and_publication"],
        attached_file_ids: ["file-mm-1-transcript"],
        operator_acknowledged_public_distribution: true,
        notes: "Approved for future public export staging; do not publish yet.",
      },
    },
  ],
};

const exportPlanRecord: MultimediaAssetRecord = {
  ...record,
  jobs: [
    ...exportReviewRecord.jobs,
    {
      job_id: "job-mm-1-0004",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 4,
      kind: "export_gate",
      status: "partial",
      progress_percent: 99,
      message: "Public export plan staged; no public URL has been minted.",
      error_code: null,
      retryable: false,
      public_export_gate: exportReviewRecord.jobs.at(-1)?.public_export_gate,
      public_export_review: exportReviewRecord.jobs.at(-1)?.public_export_review,
      public_export_plan: {
        export_id: "export-mm-1-rev-1",
        attached_file_ids: ["file-mm-1-transcript"],
        review_gate_ids: ["rights_and_publication"],
        storage_backend: "pending",
        public_url: null,
        publish_enabled: false,
      },
    },
  ],
};

const jobs = {
  jobs: record.jobs,
  count: 1,
};

const publicExportStatus: MultimediaPublicExportStatus = {
  asset_id: "mm-1",
  revision_id: "rev-1",
  gate_status: "ready",
  review_decision: "approved",
  export_id: "export-mm-1-rev-1",
  publish_blocked: true,
  publish_denial_code: "publisher_unimplemented",
  public_url: null,
  latest_job_status: "failed",
  latest_error_code: "publisher_unimplemented",
  next_required_action: "publisher_implementation",
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function mockFetch() {
  return fetch as unknown as ReturnType<typeof vi.fn>;
}

describe("multimedia API client", () => {
  it("posts a draft, lists, gets, approves, steers, and hardens", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(201, record));
    await createMultimediaDraft({ topic: "x", target_minutes: 20, mode: "hybrid", route_policy: "cheapest" });
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets",
      expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { assets: [record], count: 1 }));
    await listMultimediaAssets();
    expect(mockFetch()).toHaveBeenLastCalledWith("/multimedia/assets", expect.anything());

    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await getMultimediaAsset("mm 1");
    expect(mockFetch()).toHaveBeenLastCalledWith("/multimedia/assets/mm%201", expect.anything());

    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await approveMultimediaDryRun("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/approve-dry-run",
      expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await steerMultimediaAsset("mm-1", { prompt: "go deeper" });
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/steer",
      expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await runMultimediaHardening("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/hardening",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("lists ordered job rows via the jobs endpoint and reads latest status", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, jobs));
    const result = await listMultimediaJobs("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith("/multimedia/assets/mm-1/jobs", expect.anything());
    expect(result.count).toBe(1);
    expect(result.jobs[0].kind).toBe("render");
    expect(result.jobs[0].status).toBe("succeeded");
    // The record carries latest job status so the client does not need a
    // second status model (SPR-11: one progress contract).
    expect(record.jobs.at(-1)?.status).toBe("succeeded");
  });

  it("gets public export status without parsing job rows", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, publicExportStatus));
    const result = await getMultimediaPublicExportStatus("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/public-export-status",
      expect.anything(),
    );
    expect(result.publish_blocked).toBe(true);
    expect(result.public_url).toBeNull();
    expect(result.next_required_action).toBe("publisher_implementation");
  });

  it("surfaces a typed not-found error for a 404 job list", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(listMultimediaJobs("mm-missing")).rejects.toThrow("multimedia_asset_not_found");
  });

  it("surfaces a typed not-found error for a 404 public export status", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(getMultimediaPublicExportStatus("mm-missing")).rejects.toThrow("multimedia_asset_not_found");
  });

  it("surfaces the typed steering-clarification error on 409", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(409, { detail: "ambiguous" }));
    await expect(steerMultimediaAsset("mm-1", { prompt: "x" })).rejects.toThrow(
      "multimedia_steering_needs_clarification",
    );
  });

  it("derives failed/manual gate ids from the serialized gates array", async () => {
    if (!record.hardening_report) throw new Error("missing hardening_report");
    expect(manualGateIds(record.hardening_report)).toEqual(["rights_and_publication"]);
    expect(failedGateIds(record.hardening_report)).toEqual(["budget"]);
  });

  it("posts the live-execution preparation request to the gated endpoint", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await prepareMultimediaLiveExecution("mm-1", {
      max_budget_usd: 25,
      route_policy: "balanced",
      operator_acknowledged_spend: true,
    });
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/prepare-live-execution",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          max_budget_usd: 25,
          route_policy: "balanced",
          operator_acknowledged_spend: true,
        }),
      }),
    );
  });

  it("posts public export gate evaluation to the no-spend endpoint", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, exportGateRecord));
    const result = await evaluateMultimediaPublicExportGate("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/evaluate-public-export-gate",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.jobs.at(-1)?.kind).toBe("export_gate");
    expect(result.jobs.at(-1)?.public_export_gate?.public_export_enabled).toBe(false);
  });

  it("posts public export review to the no-spend endpoint", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, exportReviewRecord));
    const request = {
      decision: "approved" as const,
      gate_ids: ["rights_and_publication"],
      operator_acknowledged_public_distribution: true,
      notes: "Approved for future public export staging; do not publish yet.",
    };
    const result = await recordMultimediaPublicExportReview("mm-1", request);
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/public-export-review",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      }),
    );
    expect(result.jobs.at(-1)?.public_export_review?.decision).toBe("approved");
    expect(result.jobs.at(-1)?.public_export_gate?.public_export_enabled).toBe(false);
  });

  it("posts public export planning to the no-spend endpoint", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, exportPlanRecord));
    const result = await planMultimediaPublicExport("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/plan-public-export",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.jobs.at(-1)?.public_export_plan?.publish_enabled).toBe(false);
    expect(result.jobs.at(-1)?.public_export_plan?.public_url).toBeNull();
  });

  it("surfaces a typed not-found error for a 404 live-execution prep", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(
      prepareMultimediaLiveExecution("mm-missing", {
        max_budget_usd: 25,
        route_policy: "balanced",
        operator_acknowledged_spend: true,
      }),
    ).rejects.toThrow("multimedia_asset_not_found");
  });

  it("surfaces a typed not-found error for a 404 public export gate evaluation", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(evaluateMultimediaPublicExportGate("mm-missing")).rejects.toThrow("multimedia_asset_not_found");
  });

  it("surfaces a typed not-found error for a 404 public export review", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(
      recordMultimediaPublicExportReview("mm-missing", {
        decision: "approved",
        gate_ids: ["rights_and_publication"],
        operator_acknowledged_public_distribution: true,
      }),
    ).rejects.toThrow("multimedia_asset_not_found");
  });

  it("surfaces a typed not-found error for a 404 public export plan", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(planMultimediaPublicExport("mm-missing")).rejects.toThrow("multimedia_asset_not_found");
  });
});
