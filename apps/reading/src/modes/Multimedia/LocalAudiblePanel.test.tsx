import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getMultimediaLocalAudibleCapability,
  getMultimediaLocalAudiblePlayback,
  inspectMultimediaLocalAudible,
  prepareMultimediaLocalAudible,
  produceMultimediaLocalAudible,
  recoverMultimediaLocalAudible,
} from "../../api/multimedia";
import type { MultimediaAssetRecord, MultimediaLocalAudiblePreparedSet } from "../../api/multimedia";
import { LocalAudiblePanel } from "./LocalAudiblePanel";

vi.mock("../../api/multimedia", () => ({
  getMultimediaLocalAudibleCapability: vi.fn(),
  getMultimediaLocalAudiblePlayback: vi.fn(),
  inspectMultimediaLocalAudible: vi.fn(),
  prepareMultimediaLocalAudible: vi.fn(),
  produceMultimediaLocalAudible: vi.fn(),
  recoverMultimediaLocalAudible: vi.fn(),
}));

const record: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1", revision_id: "rev-1", status: "ready",
    kind: "audio_experience", title: "Aircraft factories", route_policy: "cheapest",
    requested_duration_minutes: 15, manifest: {},
  },
  plan: {}, mode: "audio", style: null, hardening_report: null,
  latest_steering_intent: null, jobs: [],
};

const setId = `mmlocalaudibleset_${"a".repeat(64)}`;
const prepared: MultimediaLocalAudiblePreparedSet = {
  set_id: setId, asset_id: "mm-1", revision_id: "rev-1",
  status: "ready_to_produce", recoverable: false, cost_usd: 0,
  playback_ready: false, total_duration_seconds: 90,
  chapters: [{
    chapter_id: "chapter-1", title: "Flow", span_count: 4, ready_span_count: 4,
    duration_seconds: 90, source_count: 1, remember_ready: true, recap_ready: true,
    learned_claim_count: 1,
  }],
};

beforeEach(() => {
  vi.mocked(getMultimediaLocalAudibleCapability).mockResolvedValue({
    available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0,
  });
  vi.mocked(prepareMultimediaLocalAudible).mockResolvedValue(prepared);
  vi.mocked(inspectMultimediaLocalAudible).mockResolvedValue(prepared);
  vi.mocked(produceMultimediaLocalAudible).mockResolvedValue({
    ...prepared, status: "registered", playback_ready: true,
  });
  vi.mocked(getMultimediaLocalAudiblePlayback).mockResolvedValue({
    asset_id: "mm-1", revision_id: "rev-1", receipt_sha256: "a".repeat(64),
    audio_sha256: "b".repeat(64), audio_size_bytes: 100, duration_seconds: 90,
    chapter_ids: ["chapter-1"], retention_marker_count: 2, learned_claim_count: 1,
    chapters: [{ chapter_id: "chapter-1", title: "Flow", sequence: 0, start_offset_seconds: 0, end_offset_seconds: 90 }],
    source_count: 1, audio_url: "/multimedia/assets/mm-1/local-audible/playback/rev-1/audio",
    learned_claims: [{
      chapter_id: "chapter-1", claim_text: "Whittle patented a turbojet design.",
      source_count: 1, follow_up_prompt: "Review the source context.",
    }],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LocalAudiblePanel", () => {
  it("prepares measured chapters, produces at zero cost, and opens verified audio", async () => {
    const onRegistered = vi.fn();
    render(<LocalAudiblePanel record={record} onRegistered={onRegistered} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare audible experience" }));
    expect(await screen.findByText("Remember + recap ready")).toBeTruthy();
    expect(screen.getByText("1 learned claim")).toBeTruthy();
    const produce = screen.getByRole("button", { name: "Produce audible experience · $0" });
    fireEvent.click(produce);
    const audio = await screen.findByLabelText("Audio playback for Aircraft factories");
    expect(audio.getAttribute("src")).toContain("/local-audible/playback/rev-1/audio");
    fireEvent.click(screen.getByRole("button", { name: "Review learned claims" }));
    expect(await screen.findByText("Whittle patented a turbojet design.")).toBeTruthy();
    expect(screen.getByText(/Review the source context/)).toBeTruthy();
    expect(onRegistered).toHaveBeenCalledOnce();
  });

  it("replaces production with explicit recovery for unknown outcomes", async () => {
    vi.mocked(prepareMultimediaLocalAudible).mockResolvedValue({
      ...prepared, status: "production_unknown", recoverable: true,
    });
    vi.mocked(recoverMultimediaLocalAudible).mockResolvedValue({
      ...prepared, status: "registered", playback_ready: true,
    });
    render(<LocalAudiblePanel record={record} onRegistered={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare audible experience" }));
    const recover = await screen.findByRole("button", { name: "Recover audible experience" });
    expect(screen.queryByRole("button", { name: "Produce audible experience · $0" })).toBeNull();
    fireEvent.click(recover);
    await screen.findByText("Verified audio ready");
  });

  it("ignores capability from a superseded revision", async () => {
    let resolveOld: ((value: { available: boolean; reason: "ready" | "unavailable"; route_policy: "cheapest"; cost_usd: 0 }) => void) | undefined;
    vi.mocked(getMultimediaLocalAudibleCapability)
      .mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0 });
    const { rerender } = render(<LocalAudiblePanel record={record} onRegistered={vi.fn()} />);
    rerender(
      <LocalAudiblePanel
        record={{ ...record, asset: { ...record.asset, revision_id: "rev-2" } }}
        onRegistered={vi.fn()}
      />,
    );
    await screen.findByRole("button", { name: "Prepare audible experience" });
    resolveOld?.({ available: false, reason: "unavailable", route_policy: "cheapest", cost_usd: 0 });
    await waitFor(() => {
      expect(screen.queryByText("Local audible production is not configured on this server.")).toBeNull();
    });
  });
});
