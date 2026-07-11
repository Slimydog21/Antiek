import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  executeChapterTtsReconciliation,
  getChapterTtsReconciliation,
  getNarrationRunReconciliation,
} from "../../api/multimedia";
import type { ChapterTtsReconciliation } from "../../api/multimedia";
import { ReconciliationPanel } from "./ReconciliationPanel";

vi.mock("../../api/multimedia", () => ({
  executeChapterTtsReconciliation: vi.fn(),
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReconciliationPanel", () => {
  it("inspects and executes only the eligible chapter action", async () => {
    vi.mocked(getChapterTtsReconciliation).mockResolvedValue(chapter);
    vi.mocked(executeChapterTtsReconciliation).mockResolvedValue({
      ...chapter,
      attempt_status: "received",
      next_action: "resume_narration",
      action_eligible: true,
      parent_resume_eligible: true,
    });
    render(<ReconciliationPanel />);
    fireEvent.change(screen.getByLabelText("Execution ID"), { target: { value: "mmexec-1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[0]);
    expect(await screen.findByText("Release stale seal")).toBeTruthy();
    expect(screen.getByTestId("chapter-reconciliation-status").textContent).toContain("$0.02");
    fireEvent.click(screen.getByRole("button", { name: "Release stale seal" }));
    await waitFor(() =>
      expect(executeChapterTtsReconciliation).toHaveBeenCalledWith("mmexec-1", "release_seal"),
    );
    expect(screen.queryByText("Release stale seal")).toBeNull();
  });

  it("shows reserved parent children and blocked count", async () => {
    vi.mocked(getNarrationRunReconciliation).mockResolvedValue({
      run_id: "run-1",
      asset_id: "asset-1",
      revision_id: "revision-parent",
      run_status: "admitted",
      blocked_chapter_count: 2,
      parent_resume_eligible: false,
      children: [
        {
          chapter_id: "chapter-0",
          execution_id: "exec-0",
          state: "sending",
          next_action: "quarantine_send",
          action_eligible: true,
          reconciliation: chapter,
        },
        {
          chapter_id: "chapter-1",
          execution_id: "exec-1",
          state: "pending",
          next_action: "wait",
          action_eligible: false,
          reconciliation: null,
        },
      ],
    });
    render(<ReconciliationPanel />);
    fireEvent.change(screen.getByLabelText("Narration run ID"), { target: { value: "run-1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[1]);
    const status = await screen.findByTestId("run-reconciliation-status");
    expect(status.textContent).toContain("chapter-0");
    expect(status.textContent).toContain("pending");
    expect(status.textContent).toContain("2");
  });

  it("surfaces unavailable runtime without stale status", async () => {
    vi.mocked(getChapterTtsReconciliation).mockRejectedValue(
      new Error("multimedia_reconciliation_runtime_unavailable"),
    );
    render(<ReconciliationPanel />);
    fireEvent.change(screen.getByLabelText("Execution ID"), { target: { value: "missing" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[0]);
    expect((await screen.findByRole("alert")).textContent).toContain("Recovery runtime unavailable");
    expect(screen.queryByTestId("chapter-reconciliation-status")).toBeNull();
  });

  it("clears a destructive action when the visible execution id changes", async () => {
    vi.mocked(getChapterTtsReconciliation).mockResolvedValue(chapter);
    render(<ReconciliationPanel />);
    const input = screen.getByLabelText("Execution ID");
    fireEvent.change(input, { target: { value: "mmexec-1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[0]);
    expect(await screen.findByText("Release stale seal")).toBeTruthy();
    fireEvent.change(input, { target: { value: "mmexec-2" } });
    expect(screen.queryByText("Release stale seal")).toBeNull();
    expect(screen.queryByTestId("chapter-reconciliation-status")).toBeNull();
  });

  it("ignores an older inspection that resolves after the visible request", async () => {
    let resolveFirst!: (value: ChapterTtsReconciliation) => void;
    let resolveSecond!: (value: ChapterTtsReconciliation) => void;
    vi.mocked(getChapterTtsReconciliation)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }));
    render(<ReconciliationPanel />);
    const input = screen.getByLabelText("Execution ID");
    fireEvent.change(input, { target: { value: "mmexec-1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[0]);
    fireEvent.change(input, { target: { value: "mmexec-2" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect" })[0]);
    resolveSecond({ ...chapter, execution_id: "mmexec-2", attempt_status: "received", next_action: "resume_narration" });
    await waitFor(() => expect(screen.getByTestId("chapter-reconciliation-status").textContent).toContain("resume narration"));
    resolveFirst(chapter);
    await Promise.resolve();
    expect(screen.getByTestId("chapter-reconciliation-status").textContent).toContain("resume narration");
    expect(screen.queryByText("Release stale seal")).toBeNull();
  });
});
