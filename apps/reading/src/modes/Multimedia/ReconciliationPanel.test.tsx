import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  executeChapterTtsReconciliation,
  getAssetReconciliationLinks,
  getChapterTtsReconciliation,
  getNarrationRunReconciliation,
} from "../../api/multimedia";
import type { AssetReconciliationLinks, ChapterTtsReconciliation } from "../../api/multimedia";
import { ReconciliationPanel } from "./ReconciliationPanel";

vi.mock("../../api/multimedia", () => ({
  executeChapterTtsReconciliation: vi.fn(),
  getAssetReconciliationLinks: vi.fn(),
  getChapterTtsReconciliation: vi.fn(),
  getNarrationRunReconciliation: vi.fn(),
}));

const chapter: ChapterTtsReconciliation = {
  execution_id: "mmexec-1",
  asset_id: "asset-1",
  revision_id: "revision-1",
  attempt_status: "sealing",
  provider_status: "succeeded",
  next_action: "release_seal",
  action_eligible: true,
  send_age_seconds: null,
  seal_age_seconds: 600,
  seal_lease_id: "lease-1",
  charged_cents: 2,
  full_ceiling_charged: true,
  raw_audio_present: true,
  raw_audio_hash_valid: true,
  requires_signed_operator_authority: true,
  requires_external_provider_evidence: false,
  parent_resume_eligible: false,
  safe_error_code: null,
};

const links: AssetReconciliationLinks = {
  asset_id: "asset-1",
  revision_id: "revision-parent",
  executions: [{
    execution_id: "mmexec-1",
    revision_id: "revision-1",
    provider: "elevenlabs",
    status: "succeeded",
    reconciliation_available: true,
  }],
  narration_runs: [{ run_id: "run-1", revision_id: "revision-parent", status: "admitted" }],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReconciliationPanel", () => {
  it("loads signed links for the selected asset and executes only its eligible action", async () => {
    vi.mocked(getAssetReconciliationLinks).mockResolvedValue(links);
    vi.mocked(getChapterTtsReconciliation).mockResolvedValue(chapter);
    vi.mocked(executeChapterTtsReconciliation).mockResolvedValue({
      ...chapter,
      attempt_status: "received",
      next_action: "resume_narration",
      parent_resume_eligible: true,
    });
    render(<ReconciliationPanel assetId="asset-1" />);
    expect(await screen.findByText("Release stale seal")).toBeTruthy();
    expect(getAssetReconciliationLinks).toHaveBeenCalledWith("asset-1");
    expect(screen.queryByLabelText("Execution ID")).toBeNull();
    expect(screen.getByTestId("chapter-reconciliation-status").textContent).toContain("$0.02");
    fireEvent.click(screen.getByRole("button", { name: "Release stale seal" }));
    await waitFor(() =>
      expect(executeChapterTtsReconciliation).toHaveBeenCalledWith("mmexec-1", "release_seal"),
    );
    expect(screen.queryByText("Release stale seal")).toBeNull();
  });

  it("opens a linked parent run without accepting a caller-entered run id", async () => {
    vi.mocked(getAssetReconciliationLinks).mockResolvedValue(links);
    vi.mocked(getChapterTtsReconciliation).mockResolvedValue(chapter);
    vi.mocked(getNarrationRunReconciliation).mockResolvedValue({
      run_id: "run-1",
      asset_id: "asset-1",
      revision_id: "revision-parent",
      run_status: "admitted",
      blocked_chapter_count: 1,
      parent_resume_eligible: false,
      children: [{
        chapter_id: "chapter-0",
        execution_id: "exec-0",
        state: "sending",
        next_action: "quarantine_send",
        action_eligible: true,
        reconciliation: chapter,
      }],
    });
    render(<ReconciliationPanel assetId="asset-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Inspect narration run admitted" }));
    const status = await screen.findByTestId("run-reconciliation-status");
    expect(getNarrationRunReconciliation).toHaveBeenCalledWith("run-1");
    expect(status.textContent).toContain("chapter-0");
    expect(status.textContent).toContain("1");
    expect(screen.queryByLabelText("Narration run ID")).toBeNull();
  });

  it("shows an honest empty state before provider execution starts", async () => {
    vi.mocked(getAssetReconciliationLinks).mockResolvedValue({
      asset_id: "asset-empty", revision_id: "rev-1", executions: [], narration_runs: [],
    });
    render(<ReconciliationPanel assetId="asset-empty" />);
    expect(await screen.findByText("No provider execution has started.")).toBeTruthy();
  });

  it("surfaces unavailable runtime without stale status", async () => {
    vi.mocked(getAssetReconciliationLinks).mockRejectedValue(
      new Error("multimedia_reconciliation_runtime_unavailable"),
    );
    render(<ReconciliationPanel assetId="asset-1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Recovery runtime unavailable");
    expect(screen.queryByTestId("chapter-reconciliation-status")).toBeNull();
  });

  it("ignores an older asset projection that resolves after asset selection changes", async () => {
    let resolveFirst!: (value: AssetReconciliationLinks) => void;
    let resolveSecond!: (value: AssetReconciliationLinks) => void;
    vi.mocked(getAssetReconciliationLinks)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }));
    const rendered = render(<ReconciliationPanel assetId="asset-1" />);
    rendered.rerender(<ReconciliationPanel assetId="asset-2" />);
    resolveSecond({ asset_id: "asset-2", revision_id: "rev-2", executions: [], narration_runs: [] });
    expect(await screen.findByText("No provider execution has started.")).toBeTruthy();
    resolveFirst(links);
    await Promise.resolve();
    expect(screen.queryByText("Release stale seal")).toBeNull();
  });
});
