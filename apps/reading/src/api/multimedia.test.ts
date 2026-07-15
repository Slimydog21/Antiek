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
  attestMultimediaVisualCandidate,
  authorizeMultimediaNarration,
  authorizeMultimediaVisual,
  createMultimediaDraft,
  failedGateIds,
  getAssetReconciliationLinks,
  getMultimediaReviewedVisualSet,
  getChapterTtsReconciliation,
  getMultimediaAsset,
  getMultimediaLocalCapability,
  getMultimediaLocalAudibleCapability,
  getMultimediaLocalAudiblePlayback,
  getMultimediaPaidAudioPlayback,
  getMultimediaPlayback,
  getNarrationRunReconciliation,
  getListeningProgress,
  materializeMultimediaVisualCandidates,
  listMultimediaAssets,
  listMultimediaJobs,
  prepareMultimediaLocal,
  prepareMultimediaLocalAudible,
  inspectMultimediaLocal,
  attestMultimediaLocalCard,
  produceMultimediaLocal,
  recoverMultimediaLocal,
  recoverMultimediaLocalAudible,
  produceMultimediaLocalAudible,
  pollMultimediaVisualGeneration,
  prepareResearchIntent,
  previewMultimediaSteering,
  previewMultimediaVisualCandidate,
  manualGateIds,
  putListeningProgress,
  runMultimediaHardening,
  registerMultimediaProduction,
  registerMultimediaReviewedVisuals,
  produceAuthorizedMultimedia,
  produceAuthorizedAudio,
  executeChapterTtsReconciliation,
  steerMultimediaAsset,
  submitMultimediaVisualGeneration,
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
  it("validates the complete local capability and prepared-set command lifecycle", async () => {
    const setId = `mmlocalset_${"a".repeat(64)}`;
    const prepared = {
      set_id: setId,
      asset_id: "mm-1",
      revision_id: "rev-1",
      status: "review_required",
      recoverable: false,
      cost_usd: 0,
      playback_ready: false,
      chapters: [{
        chapter_id: "chapter-1", title: "Flow", narration_ready: true,
        card_id: "card-1", card_ready: true, attested: false, source_count: 1,
      }],
    } as const;
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0,
    }));
    await expect(getMultimediaLocalCapability()).resolves.toMatchObject({ available: true });

    mockFetch().mockResolvedValueOnce(jsonResponse(200, prepared));
    await expect(prepareMultimediaLocal("mm-1", "rev-1")).resolves.toEqual(prepared);
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/local/prepare",
      expect.objectContaining({ body: JSON.stringify({ expected_revision_id: "rev-1" }) }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, prepared));
    await inspectMultimediaLocal("mm-1", "rev-1", setId);
    expect(mockFetch()).toHaveBeenLastCalledWith(
      `/multimedia/assets/mm-1/local/rev-1/${setId}`,
      expect.anything(),
    );

    const ready = {
      ...prepared,
      status: "ready_to_produce",
      chapters: [{ ...prepared.chapters[0], attested: true }],
    } as const;
    mockFetch().mockResolvedValueOnce(jsonResponse(200, ready));
    await attestMultimediaLocalCard("mm-1", "rev-1", setId, "card-1");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...ready, status: "production_unknown", recoverable: true,
    }));
    await produceMultimediaLocal("mm-1", "rev-1", setId);
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...ready, status: "registered", playback_ready: true,
    }));
    await recoverMultimediaLocal("mm-1", "rev-1", setId);
  });

  it("rejects drifted or dishonest local prepared-set responses", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      available: false, reason: "ready", route_policy: "cheapest", cost_usd: 0,
    }));
    await expect(getMultimediaLocalCapability()).rejects.toThrow("capability_conflict");

    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      set_id: `mmlocalset_${"a".repeat(64)}`,
      asset_id: "foreign",
      revision_id: "rev-1",
      status: "registered",
      recoverable: false,
      cost_usd: 0,
      playback_ready: false,
      chapters: [],
    }));
    await expect(prepareMultimediaLocal("mm-1", "rev-1")).rejects.toThrow(
      "local_identity_conflict",
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      set_id: `mmlocalset_${"b".repeat(64)}`,
      asset_id: "mm-1",
      revision_id: "rev-1",
      status: "ready_to_produce",
      recoverable: false,
      cost_usd: 0,
      playback_ready: false,
      chapters: [{
        chapter_id: "chapter-1", title: "Flow", narration_ready: true,
        card_id: "card-1", card_ready: true, attested: false, source_count: 1,
      }],
    }));
    await expect(prepareMultimediaLocal("mm-1", "rev-1")).rejects.toThrow(
      "local_identity_conflict",
    );
  });

  it("cross-binds the local audible lifecycle and canonical playback URL", async () => {
    const setId = `mmlocalaudibleset_${"a".repeat(64)}`;
    const prepared = {
      set_id: setId, asset_id: "mm-1", revision_id: "rev-1",
      status: "ready_to_produce", recoverable: false, cost_usd: 0,
      playback_ready: false, total_duration_seconds: 90,
      chapters: [{
        chapter_id: "chapter-1", title: "Flow", span_count: 4, ready_span_count: 4,
        duration_seconds: 90, source_count: 1, remember_ready: true, recap_ready: true,
        learned_claim_count: 1,
      }],
    } as const;
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0,
    }));
    await expect(getMultimediaLocalAudibleCapability()).resolves.toMatchObject({ available: true });
    mockFetch().mockResolvedValueOnce(jsonResponse(200, prepared));
    await expect(prepareMultimediaLocalAudible("mm-1", "rev-1")).resolves.toEqual(prepared);
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...prepared, status: "production_unknown", recoverable: true,
    }));
    await produceMultimediaLocalAudible("mm-1", "rev-1", setId);
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...prepared, status: "registered", playback_ready: true,
    }));
    await recoverMultimediaLocalAudible("mm-1", "rev-1", setId);

    const playback = {
      asset_id: "mm-1", revision_id: "rev-1", receipt_sha256: "a".repeat(64),
      audio_sha256: "b".repeat(64), audio_size_bytes: 100, duration_seconds: 90,
      chapter_ids: ["chapter-1"], retention_marker_count: 2, learned_claim_count: 1,
      chapters: [{ chapter_id: "chapter-1", title: "Flow", sequence: 0, start_offset_seconds: 0, end_offset_seconds: 90 }],
      source_count: 1,
      learned_claims: [{
        line_id: "chapter-1-line-0", chapter_id: "chapter-1", claim_text: "Verified claim", source_count: 1,
        follow_up_prompt: "Review the source.", source_chunk_ids: ["chunk-1"], evidence_status: "verified_exact",
        evidence_sources: [{ chunk_id: "chunk-1", document_id: "doc-1",
          locator: "Flow", authority_kind: "canonical_graph", chunk_sha256: "c".repeat(64),
          start_utf8_byte: 0, end_utf8_byte: 14, span_sha256: "d".repeat(64), exact_text: "Verified claim" }],
      }],
      audio_url: "/multimedia/assets/mm-1/local-audible/playback/rev-1/audio",
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, playback));
    expect((await getMultimediaLocalAudiblePlayback("mm-1", "rev-1")).audio_url).toBe(
      playback.audio_url,
    );
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...playback, audio_url: "/tmp/forged.wav",
    }));
    await expect(getMultimediaLocalAudiblePlayback("mm-1", "rev-1")).rejects.toThrow(
      "playback_identity_conflict",
    );
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...playback,
      chapters: [{ ...playback.chapters[0], end_offset_seconds: 89.998 }],
    }));
    await expect(getMultimediaLocalAudiblePlayback("mm-1", "rev-1")).rejects.toThrow(
      "playback_identity_conflict",
    );
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...playback,
      learned_claims: [{
        ...playback.learned_claims[0],
        evidence_sources: [{ ...playback.learned_claims[0].evidence_sources[0], exact_text: "Forged" }],
      }],
    }));
    await expect(getMultimediaLocalAudiblePlayback("mm-1", "rev-1")).rejects.toThrow(
      "playback_identity_conflict",
    );
  });

  it("rejects dishonest local audible readiness", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      set_id: `mmlocalaudibleset_${"a".repeat(64)}`,
      asset_id: "mm-1", revision_id: "rev-1", status: "ready_to_produce",
      recoverable: false, cost_usd: 0, playback_ready: false,
      total_duration_seconds: 1,
      chapters: [{
        chapter_id: "chapter-1", title: "Flow", span_count: 4, ready_span_count: 3,
        duration_seconds: 1, source_count: 1, remember_ready: true, recap_ready: false,
        learned_claim_count: 1,
      }],
    }));
    await expect(prepareMultimediaLocalAudible("mm-1", "rev-1")).rejects.toThrow(
      "audible_identity_conflict",
    );
  });

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

    const steeringPreview = {
      status: "ready",
      asset_id: "mm-1",
      parent_revision_id: "rev-1",
      proposed_revision_id: "rev-2",
      route_policy: "cheapest",
      intent: { steering_event_id: "steer-1", prompt: "go deeper", status: "ready", operations: [], clarifications: [], transcript: null },
      operations: [], affected_segment_ids: [], segment_reuse: [], changes: [],
      estimated_cost_delta_usd: 0, preview_token: "signed", expires_at_epoch_seconds: 2_000_000_000,
    } as const;
    mockFetch().mockResolvedValueOnce(jsonResponse(200, steeringPreview));
    await previewMultimediaSteering("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: "go deeper",
    });
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/steering-preview",
      expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, record));
    await steerMultimediaAsset("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: "go deeper",
      preview_token: "signed",
    });
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

  it("cross-binds the complete generated visual command chain", async () => {
    const authority = {
      chapter_id: "chapter-1", scene_id: "scene-1", width: 1280, height: 720,
      seed: 1, request_body_digest: "e".repeat(64),
      quote: { quote_id: "quote-1", model: "imagen-3", ceiling_microdollars: 250_000, expires_at: "2026-07-12T01:10:00Z" },
      authorization: {
        version: 2, authorization_id: "mmauth2-visual", request_id: "visual-1",
        operator_id: "owner-1", asset_id: "mm-1", revision_id: "rev-1",
        provider: "krea", route_policy: "balanced", model: "imagen-3",
        endpoint_capability: "text-to-image", catalog_version: "1",
        catalog_digest: "a".repeat(64), quote_id: "quote-1",
        quote_expires_at: "2026-07-12T01:10:00Z", recovery_authority_id: "recovery-1",
        recovery_verification_key_digest: "b".repeat(64), approved_ceiling_microdollars: 250_000,
        request_body_digest: "e".repeat(64), issued_at: "2026-07-12T01:00:00Z",
        expires_at: "2026-07-12T01:15:00Z", signature: "f".repeat(64),
      },
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, authority));
    await authorizeMultimediaVisual("mm-1", {
      request_id: "visual-1", expected_revision_id: "rev-1", chapter_id: "chapter-1",
      approved_ceiling_microdollars: 250_000, operator_acknowledged_spend: true,
    });
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/visual-authorizations",
      expect.objectContaining({ method: "POST" }),
    );

    const submitted = { execution_id: "exec-1", authorization_id: "mmauth2-visual", provider_job_id: "job-1", status: "submitted", candidate_count: 0 };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, submitted));
    await submitMultimediaVisualGeneration("mm-1", "visual-1", "rev-1", "mmauth2-visual");
    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...submitted, status: "succeeded", candidate_count: 1 }));
    await pollMultimediaVisualGeneration("mm-1", "exec-1", "rev-1", "mmauth2-visual");

    const candidates = { execution_id: "exec-1", candidates: [{ candidate_id: "candidate-1", artifact_receipt_id: "artifact-1", media_type: "image/png", byte_count: 100 }] };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, candidates));
    await materializeMultimediaVisualCandidates("mm-1", "exec-1", "visual-1", "rev-1");

    const blob = new Blob(["png"], { type: "image/png" });
    mockFetch().mockResolvedValueOnce({
      ok: true, status: 200, headers: new Headers({ "Content-Type": "image/png" }),
      blob: async () => blob,
    } as Response);
    expect(await previewMultimediaVisualCandidate("mm-1", "rev-1", "candidate-1")).toBe(blob);

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { artifact_receipt_id: "artifact-1", reviewer_id: "owner-1", attested_at: "2026-07-12T01:20:00Z" }));
    await attestMultimediaVisualCandidate("mm-1", "rev-1", "candidate-1");

    const reviewed = { set_id: "set-1", asset_id: "mm-1", revision_id: "rev-1", chapter_ids: ["chapter-1"], scene_ids: ["scene-1"], candidate_ids: ["candidate-1"], selection_digest: "c".repeat(64), created_at: "2026-07-12T01:21:00Z" };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, reviewed));
    expect((await registerMultimediaReviewedVisuals("mm-1", "rev-1", "set-request", [{ chapter_id: "chapter-1", candidate_id: "candidate-1" }])).set_id).toBe("set-1");

    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      ...authority,
      authorization: { ...authority.authorization, version: 1 },
    }));
    await expect(authorizeMultimediaVisual("mm-1", {
      request_id: "visual-1", expected_revision_id: "rev-1", chapter_id: "chapter-1",
      approved_ceiling_microdollars: 250_000, operator_acknowledged_spend: true,
    })).rejects.toThrow("identity_conflict");

    mockFetch().mockResolvedValueOnce(jsonResponse(200, { ...reviewed, scene_ids: [] }));
    await expect(registerMultimediaReviewedVisuals("mm-1", "rev-1", "set-request", [{ chapter_id: "chapter-1", candidate_id: "candidate-1" }])).rejects.toThrow("identity_conflict");

    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "missing" }));
    await expect(pollMultimediaVisualGeneration("mm-1", "exec-1", "rev-1", "mmauth2-visual")).rejects.toThrow("multimedia_visual_generation_unavailable");
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

  it("produces and reopens owner-bound paid audio", async () => {
    const authority = {
      version: 2, authorization_id: "auth-1", request_id: "request-1", operator_id: "owner-1",
      asset_id: "mm-1", revision_id: "child-1", provider: "provider", route_policy: "balanced",
      model: "tts", endpoint_capability: "text-to-speech", catalog_version: "v1",
      catalog_digest: "a".repeat(64), quote_id: "quote-1", quote_expires_at: "2026-07-12T01:10:00Z",
      recovery_authority_id: "recovery-1", recovery_verification_key_digest: "b".repeat(64),
      approved_ceiling_microdollars: 100_000, request_body_digest: "e".repeat(64),
      issued_at: "2026-07-12T01:00:00Z", expires_at: "2026-07-12T01:15:00Z",
      signature: "f".repeat(64),
    };
    const link = {
      schema_version: "antiek.multimedia-audio-production-link.v1" as const,
      owner_identity_digest: "d".repeat(64), asset_id: "mm-1", revision_id: "rev-1",
      receipt_sha256: "c".repeat(64), audio_sha256: "a".repeat(64), audio_size_bytes: 10,
      duration_seconds: 12.5,
      chapter_ids: ["chapter-1"], retention_marker_count: 1, learned_claim_count: 1,
      source_count: 1,
    };
    const paidRecord = { ...record, asset: { ...record.asset, revision_id: "rev-1" }, audio_production_link: link };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, paidRecord));
    expect((await produceAuthorizedAudio("mm-1", "rev-1", [
      { chapter_id: "chapter-1", authorization: authority },
    ])).audio_production_link?.asset_id).toBe("mm-1");
    expect(mockFetch()).toHaveBeenLastCalledWith(
      "/multimedia/assets/mm-1/audio-production", expect.objectContaining({ method: "POST" }),
    );

    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      asset_id: "mm-1", revision_id: "rev-1", receipt_sha256: "c".repeat(64),
      audio_sha256: "a".repeat(64), audio_size_bytes: 10, duration_seconds: 12.5,
      chapter_ids: ["chapter-1"], retention_marker_count: 1, learned_claim_count: 1,
      chapters: [{ chapter_id: "chapter-1", title: "Flow", sequence: 0, start_offset_seconds: 0, end_offset_seconds: 12.5 }],
      source_count: 1, learned_claims: [{ line_id: "chapter-1-line-0", chapter_id: "chapter-1", claim_text: "claim",
        source_count: 1, follow_up_prompt: "Next?", source_chunk_ids: ["chunk-1"], evidence_status: "verified_exact",
        evidence_sources: [{ chunk_id: "chunk-1", document_id: "doc-1",
          locator: null, authority_kind: "operator_excerpt", chunk_sha256: "c".repeat(64), start_utf8_byte: 0,
          end_utf8_byte: 5, span_sha256: "d".repeat(64), exact_text: "claim" }] }],
      audio_url: "/multimedia/assets/mm-1/audio-playback/rev-1/audio",
    }));
    expect((await getMultimediaPaidAudioPlayback("mm-1", "rev-1")).audio_url)
      .toBe("/multimedia/assets/mm-1/audio-playback/rev-1/audio");
  });

  it("surfaces stable steering preview conflict details", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(409, { detail: "multimedia_steering_stale_parent" }));
    await expect(steerMultimediaAsset("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: "x",
      preview_token: "signed",
    })).rejects.toThrow(
      "multimedia_steering_stale_parent",
    );
  });

  it("derives failed/manual gate ids from the serialized gates array", async () => {
    if (!record.hardening_report) throw new Error("missing hardening_report");
    expect(manualGateIds(record.hardening_report)).toEqual(["rights_and_publication"]);
    expect(failedGateIds(record.hardening_report)).toEqual(["budget"]);
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

  it("prepares research only from the exact receipt-bound claim snapshot", async () => {
    const evidence = [{
      chunk_id: "chunk-1", document_id: "doc-1", locator: "Lift",
      authority_kind: "canonical_graph" as const, chunk_sha256: "a".repeat(64),
      start_utf8_byte: 0, end_utf8_byte: 12, span_sha256: "b".repeat(64),
      exact_text: "Exact claim.",
    }];
    const claim = {
      line_id: "chapter-1-line-0", chapter_id: "chapter-1", claim_text: "Exact claim.",
      source_count: 1, follow_up_prompt: "Investigate this claim.",
      source_chunk_ids: ["chunk-1"], evidence_status: "verified_exact" as const,
      evidence_sources: evidence,
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(201, {
      intent_id: `mmri_${"c".repeat(48)}`, state: "prepared", asset_id: "asset-1",
      revision_id: "rev-1", receipt_sha256: "d".repeat(64), audio_sha256: "e".repeat(64),
      chapter_id: "chapter-1", line_id: "chapter-1-line-0", question: "Why exactly?",
      claim_text: "Exact claim.", follow_up_prompt: "Investigate this claim.",
      evidence_sources: evidence,
      evidence_digest: "4ee7ffb952a98b351bd19a70bf62dcf5897a9228acb3dffd85d3dc319c869f51",
      request_digest: "2f0f901d927328b790147bea83930b7f213fe577bbf12b1e7b7d1b440f47c00f",
      created_at: "2026-07-15T00:00:00Z", plan_handoff_status: "blocked_unowned_plan_store",
      provider_launch_authorized: false, spend_authority_digest: null,
      plan_seed: { question: "Why exactly?", intent_id: `mmri_${"c".repeat(48)}`,
        intent_digest: "f51facc43a53e88335261d424616f1a7ed13daa59b1833f448d2a56f9b2e92d4",
        evidence_digest: "4ee7ffb952a98b351bd19a70bf62dcf5897a9228acb3dffd85d3dc319c869f51" },
    }));
    await expect(prepareResearchIntent(
      "asset-1", "rev-1", "d".repeat(64), "e".repeat(64), claim,
      "Why exactly?", "request_12345678",
    )).resolves.toMatchObject({ state: "prepared", provider_launch_authorized: false });
    expect(JSON.parse(String(mockFetch().mock.calls.at(-1)?.[1]?.body))).toEqual({
      expected_revision_id: "rev-1", line_id: "chapter-1-line-0",
      question: "Why exactly?", idempotency_key: "request_12345678",
    });
  });

  it("rejects a substituted research evidence response", async () => {
    const claim = {
      line_id: "line-1", chapter_id: "chapter-1", claim_text: "Exact claim.", source_count: 1,
      follow_up_prompt: "Investigate.", source_chunk_ids: ["chunk-1"],
      evidence_status: "verified_exact" as const,
      evidence_sources: [{ chunk_id: "chunk-1", document_id: "doc-1", locator: null,
        authority_kind: "canonical_graph" as const, chunk_sha256: "a".repeat(64),
        start_utf8_byte: 0, end_utf8_byte: 12, span_sha256: "b".repeat(64), exact_text: "Exact claim." }],
    };
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      intent_id: `mmri_${"c".repeat(48)}`, state: "prepared", asset_id: "asset-1",
      revision_id: "rev-1", receipt_sha256: "d".repeat(64), audio_sha256: "e".repeat(64),
      chapter_id: "chapter-1", line_id: "line-1", question: "Why?", claim_text: "Substituted.",
      follow_up_prompt: "Investigate.", evidence_sources: claim.evidence_sources,
      evidence_digest: "f".repeat(64), request_digest: "1".repeat(64),
      created_at: "2026-07-15T00:00:00Z", plan_handoff_status: "blocked_unowned_plan_store",
      provider_launch_authorized: false, spend_authority_digest: null,
      plan_seed: { question: "Why?", intent_id: `mmri_${"c".repeat(48)}`,
        intent_digest: "2".repeat(64), evidence_digest: "f".repeat(64) },
    }));
    await expect(prepareResearchIntent(
      "asset-1", "rev-1", "d".repeat(64), "e".repeat(64), claim, "Why?", "request_12345678",
    )).rejects.toThrow("multimedia_research_intent_identity_conflict");
  });

  // ── Cycle 22: listening progress ──

  it("getListeningProgress returns resume_available=false for no row", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      resume_available: false,
      asset_id: "asset-1",
      revision_id: "rev-1",
      audio_sha256: "a".repeat(64),
      position_milliseconds: 0,
      duration_milliseconds: 120000,
      completed: false,
      session_id: "",
      sequence: 0,
      updated_at: 0,
      applied: null,
    }));
    const result = await getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120);
    expect(result.resume_available).toBe(false);
    expect(result.position_milliseconds).toBe(0);
  });

  it("getListeningProgress returns resume data when available", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      resume_available: true,
      asset_id: "asset-1",
      revision_id: "rev-1",
      audio_sha256: "a".repeat(64),
      position_milliseconds: 30000,
      duration_milliseconds: 120000,
      completed: false,
      session_id: "abcdefghijklmnop",
      sequence: 1,
      updated_at: 1000.0,
      applied: null,
    }));
    const result = await getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120);
    expect(result.resume_available).toBe(true);
    expect(result.position_milliseconds).toBe(30000);
    expect(result.session_id).toBe("abcdefghijklmnop");
  });

  it("getListeningProgress throws typed error on 404", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(404, { detail: "not found" }));
    await expect(getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120)).rejects.toThrow(
      "multimedia_listening_progress_unavailable",
    );
  });

  it("getListeningProgress throws typed error on 409", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(409, { detail: "conflict" }));
    await expect(getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120)).rejects.toThrow(
      "multimedia_listening_progress_conflict",
    );
  });

  it("getListeningProgress rejects response with mismatched asset_id", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      resume_available: true,
      asset_id: "wrong-asset",
      revision_id: "rev-1",
      audio_sha256: "a".repeat(64),
      position_milliseconds: 30000,
      duration_milliseconds: 120000,
      completed: false,
      session_id: "abcdefghijklmnop",
      sequence: 1,
      updated_at: 1000.0,
      applied: null,
    }));
    await expect(getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120)).rejects.toThrow(
      "multimedia_listening_progress_identity_conflict",
    );
  });

  it("getListeningProgress rejects contradictory completion state", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      resume_available: true,
      asset_id: "asset-1",
      revision_id: "rev-1",
      audio_sha256: "a".repeat(64),
      position_milliseconds: 119000,
      duration_milliseconds: 120000,
      completed: false,
      session_id: "abcdefghijklmnop",
      sequence: 1,
      updated_at: 1000.0,
      applied: null,
    }));
    await expect(getListeningProgress("asset-1", "rev-1", "a".repeat(64), 120)).rejects.toThrow(
      "multimedia_listening_progress_identity_conflict",
    );
  });

  it("putListeningProgress sends checkpoint and returns stored projection", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(200, {
      resume_available: true,
      asset_id: "asset-1",
      revision_id: "rev-1",
      audio_sha256: "a".repeat(64),
      position_milliseconds: 50000,
      duration_milliseconds: 120000,
      completed: false,
      session_id: "abcdefghijklmnop",
      sequence: 2,
      updated_at: 2000.0,
      applied: true,
    }));
    const result = await putListeningProgress("asset-1", {
      revision_id: "rev-1",
      position_milliseconds: 50000,
      session_id: "abcdefghijklmnop",
      sequence: 2,
    }, "a".repeat(64), 120);
    expect(result.resume_available).toBe(true);
    expect(result.position_milliseconds).toBe(50000);
    expect(result.sequence).toBe(2);
  });

  it("putListeningProgress throws typed error on 409", async () => {
    mockFetch().mockResolvedValueOnce(jsonResponse(409, { detail: "conflict" }));
    await expect(
      putListeningProgress("asset-1", {
        revision_id: "rev-1",
        position_milliseconds: 50000,
        session_id: "abcdefghijklmnop",
        sequence: 1,
      }, "a".repeat(64), 120),
    ).rejects.toThrow("multimedia_listening_progress_conflict");
  });
});
