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
  authorizeMultimediaNarration,
  createMultimediaDraft,
  failedGateIds,
  getAssetReconciliationLinks,
  getMultimediaReviewedVisualSet,
  getChapterTtsReconciliation,
  getMultimediaAsset,
  getMultimediaPlayback,
  getNarrationRunReconciliation,
  listMultimediaAssets,
  listMultimediaJobs,
  prepareMultimediaLiveExecution,
  manualGateIds,
  runMultimediaHardening,
  registerMultimediaProduction,
  produceAuthorizedMultimedia,
  executeChapterTtsReconciliation,
  steerMultimediaAsset,
} from "./multimedia";
import type { MultimediaAssetRecord } from "./multimedia";

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

const jobs = {
  jobs: record.jobs,
  count: 1,
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

  it("cross-binds playback identity and canonical media paths", async () => {
    const playback = {
      asset_id: "mm-1",
      revision_id: "rev-1",
      receipt_sha256: "c".repeat(64),
      duration_seconds: 20,
      video_sha256: "a".repeat(64),
      audio_sha256: "b".repeat(64),
      video_size_bytes: 100,
      audio_size_bytes: 80,
      width_px: 1920,
      height_px: 1080,
      chapter_ids: ["chapter-1"],
      video_url: "/multimedia/assets/mm-1/playback/rev-1/video",
      audio_url: "/multimedia/assets/mm-1/playback/rev-1/audio",
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, playback));
    expect((await getMultimediaPlayback("mm-1", "rev-1")).video_url).toBe(playback.video_url);
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/playback?revision_id=rev-1",
      expect.anything(),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...playback, revision_id: "rev-other" }));
    await expect(getMultimediaPlayback("mm-1", "rev-1")).rejects.toThrow("identity_conflict");
  });

  it("registers only the expected production revision", async () => {
    const produced = {
      ...record,
      production_link: {
        schema_version: "antiek.multimedia-production-link.v1",
        owner_identity_digest: "d".repeat(64),
        asset_id: "mm 1",
        revision_id: "rev-1",
        receipt_sha256: "c".repeat(64),
        video_sha256: "a".repeat(64),
        audio_sha256: "b".repeat(64),
        duration_seconds: 20,
        width_px: 1280,
        height_px: 720,
        chapter_ids: ["chapter-1"],
      },
      asset: { ...record.asset, asset_id: "mm 1" },
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, produced));
    await registerMultimediaProduction("mm 1", "rev-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm%201/production-registration",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_revision_id: "rev-1" }),
      }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...produced, production_link: { ...produced.production_link, revision_id: "rev-other" } }));
    await expect(registerMultimediaProduction("mm 1", "rev-1")).rejects.toThrow("identity_conflict");
  });

  it("cross-binds server-derived narration authority", async () => {
    const response = {
      chapter_id: "chapter-1",
      child_revision_id: "tts-child",
      request_body_digest: "e".repeat(64),
      authorization: {
        version: 2,
        authorization_id: "mmauth2-test",
        request_id: "request-1",
        operator_id: "owner-1",
        asset_id: "mm-1",
        revision_id: "tts-child",
        provider: "trusted-tts",
        route_policy: "balanced",
        model: "voice-1",
        endpoint_capability: "text-to-speech",
        catalog_version: "catalog-1",
        catalog_digest: "a".repeat(64),
        quote_id: "quote-1",
        quote_expires_at: "2026-07-12T01:10:00Z",
        recovery_authority_id: "recovery-1",
        recovery_verification_key_digest: "b".repeat(64),
        approved_ceiling_microdollars: 250_000,
        request_body_digest: "e".repeat(64),
        issued_at: "2026-07-12T01:00:00Z",
        expires_at: "2026-07-12T01:15:00Z",
        signature: "f".repeat(64),
      },
    };
    const request = {
      request_id: "request-1",
      expected_revision_id: "rev-1",
      chapter_id: "chapter-1",
      approved_ceiling_microdollars: 250_000,
      operator_acknowledged_spend: true as const,
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, response));
    expect((await authorizeMultimediaNarration("mm-1", request)).authorization.authorization_id).toBe("mmauth2-test");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...response, child_revision_id: "other" }));
    await expect(authorizeMultimediaNarration("mm-1", request)).rejects.toThrow("identity_conflict");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...response,
      authorization: { ...response.authorization, endpoint_capability: "image-generation" },
    }));
    await expect(authorizeMultimediaNarration("mm-1", request)).rejects.toThrow("identity_conflict");
  });

  it("cross-binds reviewed visual status to the selected revision", async () => {
    const response = {
      set_id: "mmvset-test",
      asset_id: "mm-1",
      revision_id: "rev-1",
      chapter_ids: ["chapter-1"],
      scene_ids: ["scene-chapter-1"],
      candidate_ids: ["candidate-1"],
      selection_digest: "a".repeat(64),
      created_at: "2026-07-12T01:00:00Z",
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, response));
    expect((await getMultimediaReviewedVisualSet("mm-1", "rev-1")).set_id).toBe("mmvset-test");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...response, revision_id: "rev-other" }));
    await expect(getMultimediaReviewedVisualSet("mm-1", "rev-1")).rejects.toThrow(
      "identity_conflict",
    );
  });

  it("cross-binds authorized production to the selected asset revision", async () => {
    const produced = {
      ...record,
      production_link: {
        owner_identity_digest: "a".repeat(64),
        asset_id: "mm-1",
        revision_id: "rev-1",
        receipt_sha256: "b".repeat(64),
        video_sha256: "c".repeat(64),
        audio_sha256: "d".repeat(64),
        duration_seconds: 10,
        width_px: 320,
        height_px: 240,
        chapter_ids: ["chapter-1"],
      },
    };
    const authority = {
      version: 2,
      authorization_id: "mmauth2-test",
      request_id: "request-1",
      operator_id: "owner-1",
      asset_id: "mm-1",
      revision_id: "tts-child",
      provider: "trusted-tts",
      route_policy: "balanced",
      model: "voice-1",
      endpoint_capability: "text-to-speech",
      catalog_version: "catalog-1",
      catalog_digest: "a".repeat(64),
      quote_id: "quote-1",
      quote_expires_at: "2026-07-12T01:10:00Z",
      recovery_authority_id: "recovery-1",
      recovery_verification_key_digest: "b".repeat(64),
      approved_ceiling_microdollars: 100_000,
      request_body_digest: "e".repeat(64),
      issued_at: "2026-07-12T01:00:00Z",
      expires_at: "2026-07-12T01:15:00Z",
      signature: "f".repeat(64),
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, produced));
    expect((await produceAuthorizedMultimedia("mm-1", "rev-1", [
      { chapter_id: "chapter-1", authorization: authority },
    ])).production_link?.asset_id).toBe("mm-1");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...produced,
      production_link: { ...produced.production_link, revision_id: "rev-other" },
    }));
    await expect(produceAuthorizedMultimedia("mm-1", "rev-1", [
      { chapter_id: "chapter-1", authorization: authority },
    ])).rejects.toThrow("identity_conflict");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...produced, production_link: null }));
    await expect(produceAuthorizedMultimedia("mm-1", "rev-1", [
      { chapter_id: "chapter-1", authorization: authority },
    ])).rejects.toThrow("missing_link");
  });

  it("surfaces a typed not-found error for a 404 job list", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(listMultimediaJobs("mm-missing")).rejects.toThrow("multimedia_asset_not_found");
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

  it("uses encoded mounted reconciliation endpoints", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, { asset_id: "asset 1", executions: [] }));
    await getAssetReconciliationLinks("asset 1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/asset%201/reconciliation-links",
      expect.anything(),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { execution_id: "exec 1" }));
    await getChapterTtsReconciliation("exec 1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/executions/exec%201/tts-reconciliation",
      expect.anything(),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { execution_id: "exec 1" }));
    await executeChapterTtsReconciliation("exec 1", "release_seal");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/executions/exec%201/tts-reconciliation/actions/release_seal",
      expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { run_id: "run 1" }));
    await getNarrationRunReconciliation("run 1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/narration-runs/run%201/reconciliation",
      expect.anything(),
    );
  });
});
