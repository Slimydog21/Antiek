import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attestMultimediaVisualCandidate,
  authorizeMultimediaVisual,
  materializeMultimediaVisualCandidates,
  pollMultimediaVisualGeneration,
  previewMultimediaVisualCandidate,
  registerMultimediaReviewedVisuals,
  submitMultimediaVisualGeneration,
} from "../../api/multimedia";
import type { MultimediaAssetRecord } from "../../api/multimedia";
import { VisualReviewPanel } from "./VisualReviewPanel";

vi.mock("../../api/multimedia", () => ({
  attestMultimediaVisualCandidate: vi.fn(),
  authorizeMultimediaVisual: vi.fn(),
  materializeMultimediaVisualCandidates: vi.fn(),
  pollMultimediaVisualGeneration: vi.fn(),
  previewMultimediaVisualCandidate: vi.fn(),
  registerMultimediaReviewedVisuals: vi.fn(),
  submitMultimediaVisualGeneration: vi.fn(),
}));

const record: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    status: "ready",
    kind: "documentary_video",
    title: "Aircraft factories",
    route_policy: "balanced",
    requested_duration_minutes: 15,
    manifest: {},
  },
  mode: "video",
  style: null,
  hardening_report: null,
  latest_steering_intent: null,
  jobs: [],
  plan: {
    request: { topic: "Aircraft factories", target_minutes: 15, mode: "video", route_policy: "balanced" },
    suggestions: [],
    chosen_arc_ids: ["mechanism"],
    chapters: [{ chapter_id: "chapter-1", title: "The moving line", minutes: 15, purpose: "Explain production flow", arc_id: "mechanism", source_chunk_ids: ["chunk-1"], cuts: [] }],
    script_lines: [{ line_id: "chapter-1-line-0", sequence: 0, text: "Factories moved work through fixed stations.", kind: "factual", citations: [{ chunk_id: "chunk-1", document_id: "source-1", locator: null, quote_sha256: null }], unsourced_reason: null }],
    scenes: [{ scene_id: "scene-00", chapter_id: "chapter-1", visual_intent: "Factory line", information_purpose: "Show production flow", narration_line_ids: ["chapter-1-line-0"], source_chunk_ids: ["chunk-1"] }],
    omissions: [],
    unsourced_line_ids: [],
    duration_tolerance_minutes: 0.25,
  },
};

const authorization = {
  chapter_id: "chapter-1",
  scene_id: "scene-00",
  width: 1280,
  height: 720,
  seed: 1,
  request_body_digest: "a".repeat(64),
  quote: { quote_id: "quote-1", model: "imagen-3", ceiling_microdollars: 500_000, expires_at: "2026-07-13T01:10:00Z" },
  authorization: {
    version: 2,
    authorization_id: "mmauth2-1",
    request_id: "visual-mm-1-rev-1-chapter-1",
    operator_id: "owner-1",
    asset_id: "mm-1",
    revision_id: "rev-1",
    provider: "krea",
    route_policy: "balanced",
    model: "imagen-3",
    endpoint_capability: "text-to-image",
    catalog_version: "1",
    catalog_digest: "b".repeat(64),
    quote_id: "quote-1",
    quote_expires_at: "2026-07-13T01:10:00Z",
    recovery_authority_id: "recovery-1",
    recovery_verification_key_digest: "c".repeat(64),
    approved_ceiling_microdollars: 500_000,
    request_body_digest: "a".repeat(64),
    issued_at: "2026-07-13T01:00:00Z",
    expires_at: "2026-07-13T01:15:00Z",
    signature: "d".repeat(64),
  },
};

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:candidate-1"),
    revokeObjectURL: vi.fn(),
  });
  vi.mocked(authorizeMultimediaVisual).mockResolvedValue(authorization);
  vi.mocked(submitMultimediaVisualGeneration).mockResolvedValue({ execution_id: "exec-1", authorization_id: "mmauth2-1", provider_job_id: "job-1", status: "submitted", candidate_count: 0 });
  vi.mocked(pollMultimediaVisualGeneration).mockResolvedValue({ execution_id: "exec-1", authorization_id: "mmauth2-1", provider_job_id: "job-1", status: "succeeded", candidate_count: 1 });
  vi.mocked(materializeMultimediaVisualCandidates).mockResolvedValue({ execution_id: "exec-1", candidates: [{ candidate_id: "candidate-1", artifact_receipt_id: "artifact-1", media_type: "image/png", byte_count: 1024 }] });
  vi.mocked(previewMultimediaVisualCandidate).mockResolvedValue(new Blob(["image"], { type: "image/png" }));
  vi.mocked(attestMultimediaVisualCandidate).mockResolvedValue({ artifact_receipt_id: "artifact-1", reviewer_id: "owner-1", attested_at: "2026-07-13T01:20:00Z" });
  vi.mocked(registerMultimediaReviewedVisuals).mockResolvedValue({ set_id: "set-1", asset_id: "mm-1", revision_id: "rev-1", chapter_ids: ["chapter-1"], scene_ids: ["scene-00"], candidate_ids: ["candidate-1"], selection_digest: "e".repeat(64), created_at: "2026-07-13T01:21:00Z" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("VisualReviewPanel", () => {
  it("requires spend and provenance acknowledgement before locking one complete sequence", async () => {
    const onRegistered = vi.fn();
    const { unmount } = render(<VisualReviewPanel record={record} reviewedSet={null} onRegistered={onRegistered} />);

    const authorize = screen.getByRole("button", { name: "Authorize images" });
    expect(authorize.getAttribute("disabled")).not.toBeNull();
    fireEvent.click(screen.getByLabelText("Approve this ceiling"));
    fireEvent.click(authorize);
    await screen.findByRole("button", { name: "Generate candidates" });
    fireEvent.click(screen.getByRole("button", { name: "Generate candidates" }));
    await screen.findByRole("button", { name: "Check generation" });
    fireEvent.click(screen.getByRole("button", { name: "Check generation" }));
    await screen.findByRole("button", { name: "Open contact sheet" });
    fireEvent.click(screen.getByRole("button", { name: "Open contact sheet" }));

    const select = await screen.findByRole("button", { name: "Attest & select" });
    expect(select.getAttribute("disabled")).not.toBeNull();
    fireEvent.click(screen.getByLabelText(/confirm these are generated visuals/i));
    fireEvent.click(select);
    await screen.findByRole("button", { name: "Selected" });

    const lock = screen.getByRole("button", { name: "Lock visual sequence" });
    expect(lock.getAttribute("disabled")).toBeNull();
    fireEvent.click(lock);
    await waitFor(() => expect(onRegistered).toHaveBeenCalledWith(expect.objectContaining({ set_id: "set-1" })));
    expect(registerMultimediaReviewedVisuals).toHaveBeenCalledWith(
      "mm-1",
      "rev-1",
      expect.any(String),
      [{ chapter_id: "chapter-1", candidate_id: "candidate-1" }],
    );
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:candidate-1");
  });

  it("ignores authority that resolves after the selected revision changes", async () => {
    let resolveAuthority: (value: typeof authorization) => void = () => undefined;
    vi.mocked(authorizeMultimediaVisual).mockReturnValueOnce(
      new Promise((resolve) => { resolveAuthority = resolve; }),
    );
    const { rerender } = render(<VisualReviewPanel record={record} reviewedSet={null} onRegistered={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Approve this ceiling"));
    fireEvent.click(screen.getByRole("button", { name: "Authorize images" }));
    rerender(
      <VisualReviewPanel
        record={{ ...record, asset: { ...record.asset, revision_id: "rev-2" } }}
        reviewedSet={null}
        onRegistered={vi.fn()}
      />,
    );
    await act(async () => {
      resolveAuthority(authorization);
      await Promise.resolve();
    });
    expect(screen.queryByRole("button", { name: "Generate candidates" })).toBeNull();
  });

  it("requires a fresh spend acknowledgement after changing chapters", () => {
    const plan = structuredClone(record.plan) as Record<string, unknown> & {
      chapters: Array<Record<string, unknown>>;
      script_lines: Array<Record<string, unknown>>;
      scenes: Array<Record<string, unknown>>;
    };
    plan.chapters.push({ chapter_id: "chapter-2", title: "Wing assembly", minutes: 5, purpose: "Explain wing mating", arc_id: "mechanism", source_chunk_ids: ["chunk-2"], cuts: [] });
    plan.script_lines.push({ line_id: "chapter-2-line-0", sequence: 1, text: "The wing joins the center section.", kind: "factual", citations: [{ chunk_id: "chunk-2", document_id: "source-2", locator: null, quote_sha256: null }], unsourced_reason: null });
    plan.scenes.push({ scene_id: "scene-01", chapter_id: "chapter-2", visual_intent: "Wing mating", information_purpose: "Show assembly order", narration_line_ids: ["chapter-2-line-0"], source_chunk_ids: ["chunk-2"] });
    render(<VisualReviewPanel record={{ ...record, plan }} reviewedSet={null} onRegistered={vi.fn()} />);
    const acknowledgement = screen.getByLabelText("Approve this ceiling") as HTMLInputElement;
    fireEvent.click(acknowledgement);
    expect(acknowledgement.checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Review visual chapter 2" }));
    expect((screen.getByLabelText("Approve this ceiling") as HTMLInputElement).checked).toBe(false);
  });

  it("renders a locked sequence without candidate authority details", () => {
    render(<VisualReviewPanel record={record} reviewedSet={{ set_id: "set-1", asset_id: "mm-1", revision_id: "rev-1", chapter_ids: ["chapter-1"], scene_ids: ["scene-00"], candidate_ids: ["candidate-secret"], selection_digest: "e".repeat(64), created_at: "2026-07-13T01:21:00Z" }} onRegistered={vi.fn()} />);
    expect(screen.getByText(/1 scenes bound/)).toBeTruthy();
    expect(screen.queryByText("candidate-secret")).toBeNull();
  });
});
