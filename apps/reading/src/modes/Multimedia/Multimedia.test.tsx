import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Multimedia, { formatRecordCost, shouldUseLocalAudiblePlayback } from "./index";
import {
  approveMultimediaDryRun,
  authorizeMultimediaNarration,
  createGroundedMultimediaDraft,
  createMultimediaDraft,
  getMultimediaAsset,
  getMultimediaPlayback,
  getMultimediaReviewedVisualSet,
  listMultimediaAssets,
  previewMultimediaSteering,
  runMultimediaHardening,
  searchMultimediaEvidence,
  registerMultimediaProduction,
  produceAuthorizedMultimedia,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type { MultimediaAssetRecord, MultimediaSteeringPreviewReady } from "../../api/multimedia";
import type { MultimediaPlanWire } from "../../api/multimedia";

vi.mock("./VoiceSteeringInput", () => ({
  VoiceSteeringInput: ({ value, onChange, onTranscript, onBusyChange, onDiscardTranscript }: {
    value: string;
    onChange: (value: string) => void;
    onTranscript: (value: string) => void;
    onBusyChange: (value: boolean) => void;
    onDiscardTranscript: () => void;
  }) => (
    <div>
      <textarea aria-label="Steering prompt" value={value} onChange={(event) => onChange(event.target.value)} />
      <button type="button" onClick={() => onTranscript("Go deeper on engines.")}>Use voice steer</button>
      <button type="button" onClick={() => onBusyChange(true)}>Sim capture busy</button>
      <button type="button" onClick={onDiscardTranscript}>Discard voice</button>
    </div>
  ),
}));

vi.mock("../../api/multimedia", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/multimedia")>();
  // Keep the real pure helpers (failedGateIds/manualGateIds derive from the
  // serialized `gates` array) and types; mock only the async fetch functions
  // so tests exercise the real derivation against a faithful hardening shape.
  return {
    ...actual,
    approveMultimediaDryRun: vi.fn(),
    authorizeMultimediaNarration: vi.fn(),
    createGroundedMultimediaDraft: vi.fn(),
    createMultimediaDraft: vi.fn(),
    getMultimediaAsset: vi.fn(),
    getMultimediaPlayback: vi.fn(),
    getMultimediaReviewedVisualSet: vi.fn(),
    listMultimediaAssets: vi.fn(),
    previewMultimediaSteering: vi.fn(),
    runMultimediaHardening: vi.fn(),
    searchMultimediaEvidence: vi.fn(),
    registerMultimediaProduction: vi.fn(),
    produceAuthorizedMultimedia: vi.fn(),
    steerMultimediaAsset: vi.fn(),
  };
});

const mockApprove = vi.mocked(approveMultimediaDryRun);
const mockAuthorizeNarration = vi.mocked(authorizeMultimediaNarration);
const mockCreateGrounded = vi.mocked(createGroundedMultimediaDraft);
const mockCreate = vi.mocked(createMultimediaDraft);
const mockGet = vi.mocked(getMultimediaAsset);
const mockPlayback = vi.mocked(getMultimediaPlayback);
const mockReviewedVisuals = vi.mocked(getMultimediaReviewedVisualSet);
const mockList = vi.mocked(listMultimediaAssets);
const mockPreviewSteering = vi.mocked(previewMultimediaSteering);
const mockHarden = vi.mocked(runMultimediaHardening);
const mockSearchEvidence = vi.mocked(searchMultimediaEvidence);
const mockRegisterProduction = vi.mocked(registerMultimediaProduction);
const mockProduceAuthorized = vi.mocked(produceAuthorizedMultimedia);
const mockSteer = vi.mocked(steerMultimediaAsset);

const serverPlan: MultimediaPlanWire = {
  request: { topic: "Server plan", target_minutes: 30, mode: "video", route_policy: "balanced", depth: "intermediate", selected_arc_ids: [] },
  suggestions: [{ arc_id: "mechanism", title: "Server coverage", teaches: "Learn only persisted content", evidence: [], tradeoff: "Server tradeoff" }],
  chosen_arc_ids: ["mechanism"],
  chapters: [
    { chapter_id: "server-intro", title: "Server introduction", minutes: 10, purpose: "Frame the persisted lesson.", arc_id: "intro", source_chunk_ids: [], cuts: [] },
    { chapter_id: "server-mechanism", title: "Server mechanism", minutes: 20, purpose: "Explain the persisted mechanism.", arc_id: "mechanism", source_chunk_ids: ["server-chunk"], cuts: [] },
  ],
  script_lines: [
    { line_id: "server-intro-line-0", sequence: 0, text: "This opening came from the server.", kind: "transition", citations: [], unsourced_reason: null },
    { line_id: "server-mechanism-line-0", sequence: 1, text: "The server-backed mechanism uses exact cited evidence.", kind: "factual", citations: [{ chunk_id: "server-chunk", document_id: "server-document", locator: "section 4", quote_sha256: null }], unsourced_reason: null },
  ],
  scenes: [
    { scene_id: "server-scene", chapter_id: "server-mechanism", visual_intent: "Evidence diagram", information_purpose: "Show the cited mechanism", narration_line_ids: ["server-mechanism-line-0"], source_chunk_ids: ["server-chunk"] },
  ],
  omissions: ["Server-declared omission"],
  unsourced_line_ids: [],
  duration_tolerance_minutes: 0.25,
};

const draftRecord: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    status: "planned",
    kind: "documentary_video",
    title: "The aircraft program that made cheap long-haul travel possible",
    route_policy: "balanced",
    requested_duration_minutes: 30,
    manifest: {
      cost_rows: [{ cost_usd: 40.5 }],
    },
  },
  plan: serverPlan,
  mode: "video",
  style: "Asianometry-style explainer with restrained Ken Burns motion",
  hardening_report: null,
  latest_steering_intent: null,
  jobs: [],
};

const approvedRecord: MultimediaAssetRecord = {
  ...draftRecord,
  asset: {
    ...draftRecord.asset,
    status: "ready",
    manifest: {
      cost_rows: [{ cost_usd: 40.5 }],
    },
  },
};

const steeredRecord: MultimediaAssetRecord = {
  ...draftRecord,
  asset: {
    ...draftRecord.asset,
    revision_id: "rev-2",
    parent_revision_id: "rev-1",
    steering_event_id: "steer-1",
  },
  latest_steering_intent: { prompt: "go deeper" },
};

function readySteeringPreview(prompt: string): MultimediaSteeringPreviewReady {
  return {
    status: "ready",
    asset_id: "mm-1",
    parent_revision_id: "rev-1",
    proposed_revision_id: "rev-2",
    route_policy: "balanced",
    intent: {
      steering_event_id: "steer-1",
      prompt,
      status: "ready",
      operations: [{
        operation_id: "op-1",
        kind: "deepen",
        target_kind: "chapter",
        target_id: "server-mechanism",
        value: null,
        reason: "deepen server-mechanism",
      }],
      clarifications: [],
      transcript: null,
    },
    operations: [{
      operation_id: "op-1",
      kind: "deepen",
      target_kind: "chapter",
      target_id: "server-mechanism",
      value: null,
      reason: "deepen server-mechanism",
    }],
    affected_segment_ids: ["server-mechanism"],
    segment_reuse: [
      { segment_id: "server-intro", reused: true, reason: "unaffected", file_ids: ["file-1"], file_sha256s: ["a".repeat(64)] },
      { segment_id: "server-mechanism", reused: false, reason: "targeted", file_ids: [], file_sha256s: [] },
    ],
    changes: [{
      operation_id: "op-1",
      target_id: "server-mechanism",
      changed_segment_ids: ["server-mechanism"],
      estimated_cost_delta_usd: 0.25,
      explanation: "targeted segment",
    }],
    estimated_cost_delta_usd: 0.25,
    preview_token: "signed-preview",
    expires_at_epoch_seconds: 2_000_000_000,
  };
}

const hardenedRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  hardening_report: {
    asset_id: "mm-test-001",
    revision_id: "rev-1",
    ship_status: "manual_review",
    gates: [{ gate_id: "rights_and_publication", status: "manual", findings: [] }],
    residual_risks: [],
  },
};

const producedRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  production_link: {
    schema_version: "antiek.multimedia-production-link.v1",
    owner_identity_digest: "a".repeat(64),
    asset_id: "mm-1",
    revision_id: "rev-1",
    receipt_sha256: "b".repeat(64),
    video_sha256: "c".repeat(64),
    audio_sha256: "d".repeat(64),
    duration_seconds: 10,
    width_px: 320,
    height_px: 240,
    chapter_ids: ["server-intro", "server-mechanism"],
  },
};

function narrationAuthority(chapterId: string, requestId: string) {
  return {
    chapter_id: chapterId,
    child_revision_id: `tts-${chapterId}`,
    request_body_digest: "e".repeat(64),
    authorization: {
      version: 2,
      authorization_id: `mmauth2-${chapterId}`,
      request_id: requestId,
      operator_id: "owner-1",
      asset_id: "mm-1",
      revision_id: `tts-${chapterId}`,
      provider: "trusted-tts",
      route_policy: "balanced",
      model: "voice-1",
      endpoint_capability: "text-to-speech",
      catalog_version: "catalog-1",
      catalog_digest: "a".repeat(64),
      quote_id: `quote-${chapterId}`,
      quote_expires_at: "2026-07-12T01:10:00Z",
      recovery_authority_id: "recovery-1",
      recovery_verification_key_digest: "b".repeat(64),
      approved_ceiling_microdollars: 1_000_000,
      request_body_digest: "e".repeat(64),
      issued_at: "2026-07-12T01:00:00Z",
      expires_at: "2026-07-12T01:15:00Z",
      signature: "f".repeat(64),
    },
  };
}

beforeEach(() => {
  mockProduceAuthorized.mockResolvedValue(producedRecord);
  mockReviewedVisuals.mockRejectedValue(new Error("multimedia_reviewed_visuals_unavailable"));
  mockAuthorizeNarration.mockResolvedValue(
    narrationAuthority("server-intro", "narration-server-intro"),
  );
  mockList.mockResolvedValue({
    assets: [
      {
        asset_id: "mm-1",
        revision_id: "rev-1",
        title: draftRecord.asset.title,
        kind: "documentary_video",
        status: "planned",
        requested_duration_minutes: 30,
        route_policy: "balanced",
        estimated_cost_usd: 40.5,
        hardening_status: null,
        latest_job_status: null,
        latest_job_kind: null,
      },
    ],
    count: 1,
  });
  mockCreate.mockResolvedValue(draftRecord);
  mockCreateGrounded.mockResolvedValue(draftRecord);
  mockSearchEvidence.mockResolvedValue({
    asset_id: "mm-1",
    revision_id: "rev-1",
    query: "Server plan owned corpus",
    candidates: [
      {
        chunk_id: "chunk-a",
        document_id: "doc-a",
        document_title: "Aircraft history",
        section_path: "Origins",
        excerpt: "Early aircraft history began with lightweight structures.",
        text_sha256: "a".repeat(64),
        similarity: 0.91,
      },
      {
        chunk_id: "chunk-b",
        document_id: "doc-b",
        document_title: "Engine systems",
        section_path: "Reliability",
        excerpt: "Engine design changed aircraft reliability.",
        text_sha256: "b".repeat(64),
        similarity: 0.84,
      },
    ],
  });
  mockGet.mockResolvedValue(draftRecord);
  mockPlayback.mockResolvedValue({
    asset_id: "mm-1",
    revision_id: "rev-1",
    receipt_sha256: "c".repeat(64),
    duration_seconds: 30,
    video_sha256: "a".repeat(64),
    audio_sha256: "b".repeat(64),
    video_size_bytes: 100,
    audio_size_bytes: 80,
    width_px: 1920,
    height_px: 1080,
    chapter_ids: ["server-intro", "server-mechanism"],
    video_url: "/multimedia/assets/mm-1/playback/rev-1/video",
    audio_url: "/multimedia/assets/mm-1/playback/rev-1/audio",
  });
  mockRegisterProduction.mockResolvedValue({
    ...approvedRecord,
    production_link: {
      schema_version: "antiek.multimedia-production-link.v1",
      owner_identity_digest: "d".repeat(64),
      asset_id: "mm-1",
      revision_id: "rev-1",
      receipt_sha256: "c".repeat(64),
      video_sha256: "a".repeat(64),
      audio_sha256: "b".repeat(64),
      duration_seconds: 30,
      width_px: 1920,
      height_px: 1080,
      chapter_ids: ["server-intro", "server-mechanism"],
    },
  });
  mockApprove.mockResolvedValue(approvedRecord);
  mockPreviewSteering.mockImplementation(async (_assetId, request) => readySteeringPreview(request.prompt));
  mockSteer.mockResolvedValue(steeredRecord);
  mockHarden.mockResolvedValue(hardenedRecord);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function waitForApiReady() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Review plan" }).getAttribute("disabled")).toBeNull());
}

async function reviewPlan() {
  render(<Multimedia />);
  await waitForApiReady();
  fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
  await screen.findByTestId("multimedia-suggestions");
  await waitFor(() => expect(
    (screen.getByRole("checkbox", { name: "Include Server coverage" }) as HTMLInputElement).checked,
  ).toBe(true));
}

describe("Multimedia workstation", () => {
  it("preserves legacy playback until a local audible link is registered", () => {
    const audio = {
      ...approvedRecord,
      mode: "audio" as const,
      asset: {
        ...approvedRecord.asset,
        kind: "audio_experience" as const,
        route_policy: "cheapest" as const,
      },
    };
    expect(shouldUseLocalAudiblePlayback(audio)).toBe(false);
    expect(shouldUseLocalAudiblePlayback({
      ...audio,
      audio_production_link: {
        schema_version: "antiek.multimedia-audio-production-link.v1",
        owner_identity_digest: "d".repeat(64),
        asset_id: audio.asset.asset_id,
        revision_id: audio.asset.revision_id,
        receipt_sha256: "a".repeat(64),
        audio_sha256: "b".repeat(64),
        audio_size_bytes: 44,
        duration_seconds: 30,
        chapter_ids: ["chapter-1"],
        retention_marker_count: 2,
        learned_claim_count: 1,
        source_count: 1,
      },
    })).toBe(true);
  });

  it("fails closed for malformed persisted cost rows", () => {
    const record = structuredClone(draftRecord);
    record.asset.manifest = { cost_rows: [{ cost_usd: "40.50" }] };
    expect(formatRecordCost(record, "$22.28")).toBe("Unavailable");
  });
  it("updates the estimated cost when the operator selects the cheapest route", async () => {
    render(<Multimedia />);
    await waitForApiReady();
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$40.50");

    fireEvent.click(screen.getByRole("button", { name: /Cheapest/ }));

    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$22.28");
    expect(screen.getByText(/Fully local narration and source-card documentary/)).toBeTruthy();
    expect(screen.getByText(/No Krea or paid-provider fallback/)).toBeTruthy();
  });

  it("reviews a plan before render approval and then opens playback", async () => {
    await reviewPlan();

    expect(mockCreate.mock.calls[0]?.[0]).toEqual(expect.objectContaining({
      source_scope: "Owned corpus + vetted web sources",
    }));
    expect(mockCreate.mock.calls[0]?.[0]).not.toHaveProperty("sources");

    expect(screen.getByTestId("multimedia-suggestions")).toBeTruthy();
    expect(screen.getByText(/Unsourced claim guard/)).toBeTruthy();
    expect(screen.queryByTestId("multimedia-player")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    expect(await screen.findByTestId("multimedia-player")).toBeTruthy();
    expect(mockApprove).toHaveBeenCalledWith("mm-1");
    expect(screen.getByRole("status").textContent).toContain("Partial render available");
    const video = await screen.findByLabelText(/Video playback for/);
    expect(video.getAttribute("src")).toBe("/multimedia/assets/mm-1/playback/rev-1/video");
  });

  it("reviews graph evidence and creates a separate grounded draft from exact selections", async () => {
    const user = userEvent.setup();
    const unsourced = structuredClone(draftRecord);
    const unsourcedPlan = unsourced.plan as MultimediaPlanWire;
    unsourcedPlan.script_lines[1].citations = [];
    unsourcedPlan.script_lines[1].unsourced_reason = "planner needs more graph evidence before render";
    unsourcedPlan.unsourced_line_ids = [unsourcedPlan.script_lines[1].line_id];
    unsourcedPlan.chapters[1].source_chunk_ids = [];
    unsourcedPlan.scenes[0].source_chunk_ids = [];
    mockCreate.mockResolvedValueOnce(unsourced);
    await reviewPlan();

    expect(screen.getByRole("button", { name: "Approve render" }).getAttribute("disabled")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "Find evidence" }));
    expect(await screen.findByTestId("multimedia-evidence-results")).toBeTruthy();
    expect(mockSearchEvidence).toHaveBeenCalledWith("mm-1", "rev-1");
    await user.click(screen.getByRole("checkbox", { name: "Include evidence from Engine systems" }));
    await user.click(screen.getByRole("button", { name: "Create grounded draft" }));

    await waitFor(() => expect(mockCreateGrounded).toHaveBeenCalledWith(
      "mm-1",
      "rev-1",
      [expect.objectContaining({ chunk_id: "chunk-a", text_sha256: "a".repeat(64) })],
    ));
  });

  it("persists a focused draft from selected generated coverage", async () => {
    const user = userEvent.setup();
    await reviewPlan();

    const coverage = screen.getByRole("checkbox", { name: "Include Server coverage" });
    const focused = screen.getByRole("button", { name: "Create focused draft" });
    expect((coverage as HTMLInputElement).checked).toBe(true);
    await user.click(coverage);
    expect(focused.getAttribute("disabled")).not.toBeNull();

    await user.click(coverage);
    await user.click(screen.getByRole("radio", { name: "deep" }));
    await user.click(focused);

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(2));
    expect(mockCreate.mock.calls[1]?.[0]).toEqual(expect.objectContaining({
      depth: "deep",
      selected_arc_ids: ["mechanism"],
    }));
  });

  it("requires explicit ceiling acknowledgement before issuing narration authority", async () => {
    const user = userEvent.setup();
    await reviewPlan();
    const authorize = screen.getByRole("button", { name: "Authorize narration" });
    expect(authorize.getAttribute("disabled")).not.toBeNull();
    const acknowledgement = screen.getByRole("checkbox", { name: "Approve this maximum" });
    await user.click(acknowledgement);
    expect((acknowledgement as HTMLInputElement).checked).toBe(true);
    await waitFor(() => expect(
      screen.getByRole("button", { name: "Authorize narration" }).getAttribute("disabled"),
    ).toBeNull(), { timeout: 5_000 });
    fireEvent.click(screen.getByRole("button", { name: "Authorize narration" }));

    await waitFor(() => expect(mockAuthorizeNarration).toHaveBeenCalledWith(
      "mm-1",
      expect.objectContaining({
        chapter_id: "server-intro",
        approved_ceiling_microdollars: 1_000_000,
        operator_acknowledged_spend: true,
      }),
    ));
    expect(await screen.findByText("mmauth2-server-intro")).toBeTruthy();
    expect(screen.getByText("trusted-tts / voice-1")).toBeTruthy();
  }, 15_000);

  it("shows only owner-bound reviewed visual readiness", async () => {
    mockReviewedVisuals.mockResolvedValueOnce({
      set_id: "mmvset-test",
      asset_id: "mm-1",
      revision_id: "rev-1",
      chapter_ids: ["server-intro", "server-mechanism"],
      scene_ids: ["scene-server-intro", "scene-server-mechanism"],
      candidate_ids: ["candidate-1", "candidate-2"],
      selection_digest: "a".repeat(64),
      created_at: "2026-07-12T01:00:00Z",
    });
    await reviewPlan();
    expect(await screen.findByText("2 scenes bound")).toBeTruthy();
    expect(screen.getByText("mmvset-test")).toBeTruthy();
    expect(screen.queryByText("candidate-1")).toBeNull();
  });

  it("distinguishes reviewed visual runtime failure from no reviewed set", async () => {
    mockReviewedVisuals.mockRejectedValueOnce(
      new Error("multimedia_reviewed_visuals_runtime_unavailable"),
    );
    await reviewPlan();
    expect(await screen.findByText("Status unavailable")).toBeTruthy();
    expect(screen.queryByText("Awaiting reviewed candidates")).toBeNull();
  });

  it("accumulates exact chapter authorities before producing", async () => {
    const user = userEvent.setup();
    mockReviewedVisuals.mockResolvedValueOnce({
      set_id: "mmvset-test",
      asset_id: "mm-1",
      revision_id: "rev-1",
      chapter_ids: ["server-intro", "server-mechanism"],
      scene_ids: ["scene-server-intro", "scene-server-mechanism"],
      candidate_ids: ["candidate-1", "candidate-2"],
      selection_digest: "a".repeat(64),
      created_at: "2026-07-12T01:00:00Z",
    });
    mockAuthorizeNarration.mockImplementation(async (_assetId, request) =>
      narrationAuthority(request.chapter_id, request.request_id),
    );
    await reviewPlan();
    const produce = await screen.findByRole("button", { name: "Produce documentary" });
    expect(produce.getAttribute("disabled")).not.toBeNull();

    const authorizeSelectedChapter = async () => {
      await user.click(screen.getByLabelText("Approve this maximum"));
      const authorize = screen.getByRole("button", { name: "Authorize narration" });
      await waitFor(() => expect(authorize.getAttribute("disabled")).toBeNull());
      await user.click(authorize);
    };

    await authorizeSelectedChapter();
    await screen.findByText("mmauth2-server-intro");
    await user.click(screen.getByRole("button", { name: "Select storyboard chapter 2" }));
    await authorizeSelectedChapter();
    await screen.findByText("mmauth2-server-mechanism");

    await waitFor(() => expect(produce.getAttribute("disabled")).toBeNull());
    fireEvent.click(produce);
    await waitFor(() => expect(mockProduceAuthorized).toHaveBeenCalledWith(
      "mm-1",
      "rev-1",
      [
        expect.objectContaining({ chapter_id: "server-intro" }),
        expect.objectContaining({ chapter_id: "server-mechanism" }),
      ],
    ));
  });

  it("does not present simulated media when verified playback is unavailable", async () => {
    mockPlayback.mockRejectedValueOnce(new Error("multimedia_playback_unavailable"));
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByText("No verified media receipt");
    expect(screen.queryByLabelText(/Video playback for/)).toBeNull();
    expect(screen.queryByText("Ken Burns preview")).toBeNull();
  });

  it("registers an existing verified receipt before presenting produced media", async () => {
    mockPlayback.mockRejectedValueOnce(new Error("multimedia_playback_unavailable"));
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    const register = await screen.findByRole("button", { name: "Register produced media" });
    fireEvent.click(register);

    await waitFor(() => expect(mockRegisterProduction).toHaveBeenCalledWith("mm-1", "rev-1"));
    expect(await screen.findByLabelText(/Video playback for/)).toBeTruthy();
  });

  it("blocks approval while the persisted plan contains an unsourced factual line", async () => {
    const record = structuredClone(draftRecord);
    const plan = structuredClone(serverPlan);
    plan.script_lines[0].kind = "factual";
    plan.script_lines[0].unsourced_reason = "needs an opening source";
    plan.unsourced_line_ids = [plan.script_lines[0].line_id];
    record.plan = plan;
    mockCreate.mockResolvedValueOnce(record);

    await reviewPlan();

    expect(screen.getByRole("button", { name: "Approve render" }).getAttribute("disabled")).not.toBeNull();
    expect(screen.getByText(/needs an opening source/)).toBeTruthy();
  });

  it("surfaces provider unavailable and lets the operator downgrade safely", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: "Sim provider down" }));

    expect(screen.getByRole("status").textContent).toContain("Krea provider unavailable");

    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));

    expect(screen.getByRole("status").textContent).toContain("Partial render available");
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$40.50");
  });

  it("surfaces an over-budget state with the same downgrade path", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: "Sim over budget" }));

    expect(screen.getByRole("status").textContent).toContain("Over budget");
    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));
    expect(screen.getByRole("status").textContent).toContain("Partial render available");
  });

  it("highlights the current transcript segment and source card when a chapter is inspected", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: /Server mechanism/ }));

    const transcript = screen.getByTestId("multimedia-transcript");
    expect(within(transcript).getByText(/server-backed mechanism uses exact cited evidence/)).toBeTruthy();
    expect(screen.getByTestId("multimedia-source-detail").textContent).toContain("section 4");
  });

  it("renders persisted plan truth instead of the aircraft fixture", async () => {
    await reviewPlan();
    expect(screen.getByText("Server introduction")).toBeTruthy();
    expect(screen.getByText("Server-declared omission")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");
    expect(screen.getByText(/This opening came from the server/)).toBeTruthy();
    expect(screen.queryByText("The engineering constraint stack")).toBeNull();
  });

  it("lists and reopens persisted multimedia assets", async () => {
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /The aircraft program/ }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-1"));
    expect(await screen.findByText(/mm-1 \/ rev-1/)).toBeTruthy();
  });

  it("previews scope and cost before applying through the API client", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await waitFor(() => expect(mockPreviewSteering).toHaveBeenCalledWith("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: expect.any(String),
    }));
    const preview = await screen.findByTestId("multimedia-steering-preview");
    expect(preview.textContent).toContain("Incremental cost: $0.2500");
    expect(preview.textContent).toContain("Affected: 1 segments");
    expect(preview.textContent).toContain("Reused: 1 segments");
    expect(mockSteer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apply preview" }));
    await waitFor(() => expect(mockSteer).toHaveBeenCalledWith("mm-1", {
      expected_parent_revision_id: "rev-1",
      preview_token: "signed-preview",
      prompt: expect.any(String),
    }));
    expect(await screen.findByText(/mm-1 \/ rev-2/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Run hardening" }));
    await waitFor(() => expect(mockHarden).toHaveBeenCalledWith("mm-1"));
    expect(await screen.findByText(/Hardening: manual_review/)).toBeTruthy();
    expect(screen.getByText(/rights_and_publication/)).toBeTruthy();
  });

  it("persists raw and corrected voice steering only after explicit apply", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Use voice steer" }));
    expect(mockSteer).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Steering prompt"), {
      target: { value: "Go deeper on engine reliability." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });
    fireEvent.click(screen.getByRole("button", { name: "Apply preview" }));

    await waitFor(() => expect(mockSteer).toHaveBeenCalledWith("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: "Go deeper on engine reliability.",
      raw_voice_transcript: "Go deeper on engines.",
      corrected_voice_transcript: "Go deeper on engine reliability.",
      preview_token: "signed-preview",
    }));
  });

  it("omits a correction when the reviewed voice transcript is unchanged", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Use voice steer" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });
    fireEvent.click(screen.getByRole("button", { name: "Apply preview" }));

    await waitFor(() => expect(mockSteer).toHaveBeenCalledWith("mm-1", {
      expected_parent_revision_id: "rev-1",
      prompt: "Go deeper on engines.",
      raw_voice_transcript: "Go deeper on engines.",
      preview_token: "signed-preview",
    }));
  });

  it("blocks preview while microphone or transcription work is active", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Sim capture busy" }));
    const preview = screen.getByRole("button", { name: "Preview steer" }) as HTMLButtonElement;

    expect(preview.disabled).toBe(true);
    fireEvent.click(preview);
    expect(mockPreviewSteering).not.toHaveBeenCalled();
    expect(mockSteer).not.toHaveBeenCalled();
  });

  it("returns a discarded voice transcript to an exact text-only payload", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Use voice steer" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard voice" }));
    fireEvent.change(screen.getByLabelText("Steering prompt"), { target: { value: "typed replacement" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });
    fireEvent.click(screen.getByRole("button", { name: "Apply preview" }));

    await waitFor(() => expect(mockSteer).toHaveBeenCalledWith("mm-1", {
      expected_parent_revision_id: "rev-1",
      preview_token: "signed-preview",
      prompt: "typed replacement",
    }));
  });

  it("renders structured clarification without granting Apply authority", async () => {
    mockPreviewSteering.mockResolvedValueOnce({
      status: "needs_clarification",
      asset_id: "mm-1",
      parent_revision_id: "rev-1",
      intent: {
        steering_event_id: "steer-clarify",
        prompt: "make it better",
        status: "needs_clarification",
        operations: [],
        clarifications: ["Name the chapter or scene to change."],
        transcript: null,
      },
    });
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    expect(await screen.findByText("Name the chapter or scene to change.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Apply preview" })).toBeNull();
    expect(mockSteer).not.toHaveBeenCalled();
  });

  it("invalidates reviewed authority when the steering text changes", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });

    fireEvent.change(screen.getByLabelText("Steering prompt"), { target: { value: "new scope" } });

    expect(screen.queryByRole("button", { name: "Apply preview" })).toBeNull();
    expect(screen.queryByTestId("multimedia-steering-preview")).toBeNull();
  });

  it("invalidates reviewed authority when the outline preset changes the prompt", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });

    fireEvent.click(screen.getByRole("button", { name: "Steer outline" }));

    expect(screen.queryByRole("button", { name: "Apply preview" })).toBeNull();
    expect(screen.queryByTestId("multimedia-steering-preview")).toBeNull();
    expect((screen.getByLabelText("Steering prompt") as HTMLTextAreaElement).value).toContain("Shorten");
  });

  it("retires an already-expired preview without calling Apply", async () => {
    mockPreviewSteering.mockResolvedValueOnce({
      ...readySteeringPreview("go deeper"),
      expires_at_epoch_seconds: 1,
    });
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));

    expect(await screen.findByText(/preview expired/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Apply preview" })).toBeNull();
    expect(mockSteer).not.toHaveBeenCalled();
  });

  it("submits one Apply when the reviewed authority is double-clicked", async () => {
    let resolveApply: ((value: MultimediaAssetRecord) => void) | undefined;
    mockSteer.mockReturnValueOnce(
      new Promise<MultimediaAssetRecord>((resolve) => { resolveApply = resolve; }),
    );
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    const apply = await screen.findByRole("button", { name: "Apply preview" });

    fireEvent.click(apply);
    fireEvent.click(apply);

    expect(mockSteer).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Applying reviewed revision...")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Steer outline" }) as HTMLButtonElement).disabled).toBe(true);
    resolveApply?.(steeredRecord);
    expect(await screen.findByText(/mm-1 \/ rev-2/)).toBeTruthy();
  });

  it("ignores an older preview response after a newer input snapshot", async () => {
    let resolveFirst: ((value: MultimediaSteeringPreviewReady) => void) | undefined;
    mockPreviewSteering
      .mockReturnValueOnce(new Promise<MultimediaSteeringPreviewReady>((resolve) => { resolveFirst = resolve; }))
      .mockImplementationOnce(async (_assetId, request) => readySteeringPreview(request.prompt));
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    fireEvent.change(screen.getByLabelText("Steering prompt"), { target: { value: "newer chapter scope" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    expect((await screen.findByTestId("multimedia-steering-preview")).textContent).toContain("deepen server-mechanism");

    resolveFirst?.({ ...readySteeringPreview("obsolete scope"), estimated_cost_delta_usd: 9 });
    await Promise.resolve();

    expect(screen.getByTestId("multimedia-steering-preview").textContent).toContain("$0.2500");
    expect(screen.getByRole("button", { name: "Apply preview" })).toBeTruthy();
  });

  it("drops stale authority and reopens the current asset revision", async () => {
    mockSteer.mockRejectedValueOnce(new Error("multimedia_steering_stale_parent"));
    mockGet.mockResolvedValueOnce({
      ...draftRecord,
      asset: { ...draftRecord.asset, revision_id: "rev-current" },
    });
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Preview steer" }));
    await screen.findByRole("button", { name: "Apply preview" });

    fireEvent.click(screen.getByRole("button", { name: "Apply preview" }));

    expect(await screen.findByText(/changed after preview/)).toBeTruthy();
    expect(mockGet).toHaveBeenCalledWith("mm-1");
    expect(screen.queryByRole("button", { name: "Apply preview" })).toBeNull();
  });

  it("keeps the fixture preview visible when the API is unavailable", async () => {
    mockCreate.mockRejectedValueOnce(new Error("offline"));
    render(<Multimedia />);
    await waitForApiReady();

    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Could not create");
    expect(screen.getByTestId("multimedia-suggestions")).toBeTruthy();
  });
});
