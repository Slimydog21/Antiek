import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attestMultimediaLocalCard,
  getMultimediaLocalCapability,
  inspectMultimediaLocal,
  prepareMultimediaLocal,
  produceMultimediaLocal,
  recoverMultimediaLocal,
} from "../../api/multimedia";
import type { MultimediaAssetRecord, MultimediaLocalPreparedSet } from "../../api/multimedia";
import { LocalProductionPanel } from "./LocalProductionPanel";

vi.mock("../../api/multimedia", () => ({
  attestMultimediaLocalCard: vi.fn(),
  getMultimediaLocalCapability: vi.fn(),
  inspectMultimediaLocal: vi.fn(),
  multimediaLocalCardPreviewUrl: vi.fn(() => "/local-card.png"),
  prepareMultimediaLocal: vi.fn(),
  produceMultimediaLocal: vi.fn(),
  recoverMultimediaLocal: vi.fn(),
}));

const record: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1", revision_id: "rev-1", status: "ready",
    kind: "documentary_video", title: "Aircraft factories", route_policy: "cheapest",
    requested_duration_minutes: 15, manifest: {},
  },
  plan: {}, mode: "video", style: null, hardening_report: null,
  latest_steering_intent: null, jobs: [],
};

const setId = `mmlocalset_${"a".repeat(64)}`;
const prepared: MultimediaLocalPreparedSet = {
  set_id: setId, asset_id: "mm-1", revision_id: "rev-1",
  status: "review_required", recoverable: false, cost_usd: 0,
  playback_ready: false,
  chapters: [{
    chapter_id: "chapter-1", title: "Flow", narration_ready: true,
    card_id: "card-1", card_ready: true, attested: false, source_count: 1,
  }],
};

beforeEach(() => {
  vi.mocked(getMultimediaLocalCapability).mockResolvedValue({
    available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0,
  });
  vi.mocked(prepareMultimediaLocal).mockResolvedValue(prepared);
  vi.mocked(inspectMultimediaLocal).mockResolvedValue(prepared);
  vi.mocked(attestMultimediaLocalCard).mockResolvedValue({
    ...prepared, status: "ready_to_produce",
    chapters: [{ ...prepared.chapters[0], attested: true }],
  });
  vi.mocked(produceMultimediaLocal).mockResolvedValue({
    ...prepared, status: "registered", playback_ready: true,
    chapters: [{ ...prepared.chapters[0], attested: true }],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LocalProductionPanel", () => {
  it("requires explicit card attestation before local production", async () => {
    const onRegistered = vi.fn();
    render(<LocalProductionPanel record={record} onRegistered={onRegistered} />);
    await screen.findByRole("button", { name: "Prepare local chapters" });
    fireEvent.click(screen.getByRole("button", { name: "Prepare local chapters" }));
    await screen.findByRole("img", { name: "Source card for Flow" });
    expect(screen.getByText("Review required")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Attest source card" }));
    const produce = await screen.findByRole("button", { name: "Produce locally · $0" });
    expect(produce.getAttribute("disabled")).toBeNull();
    fireEvent.click(produce);
    await screen.findByText("Verified playback ready");
    expect(onRegistered).toHaveBeenCalledOnce();
  });

  it("replaces production with the explicit recovery command", async () => {
    vi.mocked(prepareMultimediaLocal).mockResolvedValue({
      ...prepared, status: "production_unknown", recoverable: true,
      chapters: [{ ...prepared.chapters[0], attested: true }],
    });
    vi.mocked(recoverMultimediaLocal).mockResolvedValue({
      ...prepared, status: "registered", playback_ready: true,
      chapters: [{ ...prepared.chapters[0], attested: true }],
    });
    render(<LocalProductionPanel record={record} onRegistered={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare local chapters" }));
    const recover = await screen.findByRole("button", { name: "Recover local production" });
    expect(screen.queryByRole("button", { name: "Produce locally · $0" })).toBeNull();
    fireEvent.click(recover);
    await screen.findByText("Verified playback ready");
  });

  it("ignores capability responses from a superseded revision", async () => {
    let resolveOld: ((value: { available: boolean; reason: "ready" | "unavailable"; route_policy: "cheapest"; cost_usd: 0 }) => void) | undefined;
    vi.mocked(getMultimediaLocalCapability)
      .mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ available: true, reason: "ready", route_policy: "cheapest", cost_usd: 0 });
    const { rerender } = render(<LocalProductionPanel record={record} onRegistered={vi.fn()} />);
    rerender(
      <LocalProductionPanel
        record={{ ...record, asset: { ...record.asset, revision_id: "rev-2" } }}
        onRegistered={vi.fn()}
      />,
    );
    await screen.findByRole("button", { name: "Prepare local chapters" });
    resolveOld?.({ available: false, reason: "unavailable", route_policy: "cheapest", cost_usd: 0 });
    await waitFor(() => {
      expect(screen.queryByText("Local production is not configured on this server.")).toBeNull();
    });
  });
});
