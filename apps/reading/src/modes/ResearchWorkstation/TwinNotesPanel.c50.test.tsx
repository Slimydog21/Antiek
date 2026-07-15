import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TwinNotesPanel from "./TwinNotesPanel";

const discover = vi.fn();
const list = vi.fn();
const preview = vi.fn();
const apply = vi.fn();
const history = vi.fn();

vi.mock("../../api/research", async (load) => {
  const actual = await load<typeof import("../../api/research")>();
  return {
    ...actual,
    discoverTwinNoteRevisionCandidates: (...args: unknown[]) => discover(...args),
    listTwinNotes: (...args: unknown[]) => list(...args),
    getTwinNoteHistory: (...args: unknown[]) => history(...args),
    composeTwinNotes: vi.fn(),
    previewTwinNoteRevision: (...args: unknown[]) => preview(...args),
    applyTwinNoteRevision: (...args: unknown[]) => apply(...args),
    createTwinNoteWriteDraft: vi.fn(),
  };
});

const candidateResponse = {
  assets: [{
    asset_id: "asset-owned",
    asset_label: "Field notes",
    truncated: false,
    windows: [
      { window_id: "window-a", investigation_id: "investigation-1", consumer_version: 20, window_ordinal: 1, note_count: 2, source_count: 3, eligibility: "eligible", exclusion_reason: null },
      { window_id: "window-b", investigation_id: "investigation-2", consumer_version: 20, window_ordinal: 2, note_count: 1, source_count: 1, eligibility: "eligible", exclusion_reason: null },
      { window_id: "window-bad", investigation_id: "investigation-3", consumer_version: 20, window_ordinal: 3, note_count: 0, source_count: 0, eligibility: "excluded", exclusion_reason: "evidence_digest_mismatch" },
    ],
  }],
  truncated: false,
  limits: { assets: 20, windows_per_asset: 50, total_windows: 500, selection_members: 20 },
};

describe("Cycle 50 revision candidate discovery", () => {
  beforeEach(() => {
    discover.mockReset().mockResolvedValue(candidateResponse);
    list.mockReset().mockResolvedValue({ assets: [] });
    preview.mockReset();
    apply.mockReset();
    history.mockReset().mockResolvedValue({ asset_id: "asset-owned", revisions: [] });
  });

  afterEach(() => cleanup());

  it("removes caller identity fields and shows owned candidates with safe exclusions", async () => {
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    expect(screen.queryByLabelText("Twin-note asset ID")).toBeNull();
    expect(screen.queryByLabelText("Ordered window IDs")).toBeNull();

    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    expect(screen.getByText("Evidence verification failed")).toBeTruthy();
    expect((screen.getByLabelText("Add window window-bad") as HTMLButtonElement).disabled).toBe(true);
  });

  it("preserves click order, prevents duplicates, reorders, removes, and previews exactly", async () => {
    preview.mockResolvedValue({
      asset_id: "asset-owned",
      expected_predecessor: null,
      preview_digest: "a".repeat(64),
      members: [
        { member_ordinal: 0, investigation_id: "investigation-1", window_id: "window-a" },
        { member_ordinal: 1, investigation_id: "investigation-2", window_id: "window-b" },
      ],
      note_count: 3,
      source_count: 4,
    });
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-b"));
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    expect((screen.getByLabelText("Add window window-b") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Move window window-a up"));
    fireEvent.click(screen.getByText("Preview"));
    await waitFor(() => expect(preview).toHaveBeenCalledWith("asset-owned", ["window-a", "window-b"]));

    fireEvent.click(screen.getByLabelText("Remove window window-a"));
    expect(screen.queryByLabelText("Revision preview")).toBeNull();
    expect(screen.getByText("1/20 windows selected")).toBeTruthy();
  });

  it("retains an ambiguous apply command and refreshes history plus discovery after success", async () => {
    preview.mockResolvedValue({
      asset_id: "asset-owned",
      expected_predecessor: "tnr-" + "1".repeat(32),
      preview_digest: "b".repeat(64),
      members: [{ member_ordinal: 0, investigation_id: "investigation-1", window_id: "window-a" }],
      note_count: 2,
      source_count: 3,
    });
    apply.mockRejectedValueOnce(new Error("unknown outcome")).mockResolvedValueOnce({ revision_id: "tnr-" + "2".repeat(32) });
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    fireEvent.click(screen.getByText("Preview"));
    await screen.findByLabelText("Revision preview");
    fireEvent.click(screen.getByText("Apply revision"));
    await screen.findByRole("alert");
    const firstCommand = apply.mock.calls[0][0];
    expect(screen.getByText("1/20 windows selected")).toBeTruthy();

    fireEvent.click(screen.getByText("Apply revision"));
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(2));
    expect(apply.mock.calls[1][0]).toEqual(firstCommand);
    await waitFor(() => expect(discover).toHaveBeenCalledTimes(2));
    expect(list).toHaveBeenCalledTimes(2);
    expect(history).toHaveBeenCalledWith("asset-owned");
  });

  it("rotates the apply command for every semantic selection change and discovery refresh", async () => {
    preview.mockImplementation((assetId: string, windowIds: string[]) => Promise.resolve({
      asset_id: assetId,
      expected_predecessor: null,
      preview_digest: "c".repeat(64),
      members: windowIds.map((window_id, member_ordinal) => ({ member_ordinal, investigation_id: "investigation", window_id })),
      note_count: 1,
      source_count: 1,
    }));
    apply.mockRejectedValue(new Error("retain for inspection"));
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));

    const applyCurrentPreview = async () => {
      fireEvent.click(screen.getByText("Preview"));
      await screen.findByLabelText("Revision preview");
      fireEvent.click(screen.getByText("Apply revision"));
      await screen.findByRole("alert");
    };

    await applyCurrentPreview();
    fireEvent.click(screen.getByLabelText("Add window window-b"));
    await applyCurrentPreview();
    fireEvent.click(screen.getByLabelText("Move window window-b up"));
    await applyCurrentPreview();
    fireEvent.click(screen.getByLabelText("Remove window window-a"));
    await applyCurrentPreview();
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    await applyCurrentPreview();
    fireEvent.click(screen.getByLabelText("Refresh twin notes"));
    await waitFor(() => expect(discover).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText("Revision preview")).toBeNull();
    expect(screen.getByText("1/20 windows selected")).toBeTruthy();
    await applyCurrentPreview();

    const keys = apply.mock.calls.map(([command]) => command.idempotency_key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("freezes discovery, revision, legacy, history, open, compose, and import controls together", async () => {
    const revisions = ["a", "b"].map((letter) => `tnr-${letter.repeat(32)}`);
    list.mockResolvedValue({ assets: revisions.map((revision_id, index) => ({
      asset_id: `legacy-${index}`,
      asset_label: `Legacy ${index}`,
      current_revision: { revision_id, asset_id: `legacy-${index}`, note_count: 1, source_count: 1 },
      revision_count: 1,
    })) });
    let finishPreview: ((value: unknown) => void) | undefined;
    preview.mockReturnValue(new Promise((resolve) => { finishPreview = resolve; }));
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.click(screen.getByLabelText("Select current Legacy 0"));
    fireEvent.click(screen.getByLabelText("Select current Legacy 1"));
    fireEvent.click(screen.getAllByText("Create Write draft")[0]);
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    fireEvent.click(screen.getByText("Preview"));
    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));

    expect((screen.getByLabelText("Refresh twin notes") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText("Twin-note asset").matches(":disabled")).toBe(true);
    expect(screen.getByLabelText("Add window window-b").matches(":disabled")).toBe(true);
    expect(screen.getByLabelText("Remove window window-a").matches(":disabled")).toBe(true);
    expect((screen.getByLabelText("Select current Legacy 0") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getAllByText("Open current")[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getAllByText("History")[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Compose twin notes") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText("Write draft title").matches(":disabled")).toBe(true);

    finishPreview?.({ asset_id: "asset-owned", expected_predecessor: null, preview_digest: "d".repeat(64), members: [{ member_ordinal: 0, investigation_id: "investigation-1", window_id: "window-a" }], note_count: 1, source_count: 1 });
    await screen.findByLabelText("Revision preview");
  });

  it("refuses an older discovery generation without leaking its asset", async () => {
    let finishOld: ((value: typeof candidateResponse) => void) | undefined;
    let finishNew: ((value: typeof candidateResponse) => void) | undefined;
    const oldResponse = { ...candidateResponse, assets: [{ ...candidateResponse.assets[0], asset_id: "old", asset_label: "Old result" }] };
    const newResponse = { ...candidateResponse, assets: [{ ...candidateResponse.assets[0], asset_id: "new", asset_label: "New result" }] };
    discover
      .mockReturnValueOnce(new Promise<typeof candidateResponse>((resolve) => { finishOld = resolve; }))
      .mockReturnValueOnce(new Promise<typeof candidateResponse>((resolve) => { finishNew = resolve; }));
    render(<StrictMode><TwinNotesPanel /></StrictMode>);
    finishNew?.(newResponse);
    expect(await screen.findByRole("option", { name: "New result" })).toBeTruthy();
    finishOld?.(oldResponse);
    await waitFor(() => expect(screen.queryByRole("option", { name: "Old result" })).toBeNull());
  });

  it("fails closed on a mismatched preview echo while retaining the exact selection", async () => {
    preview.mockResolvedValue({
      asset_id: "different-asset",
      expected_predecessor: null,
      preview_digest: "e".repeat(64),
      members: [{ member_ordinal: 0, investigation_id: "investigation-1", window_id: "different-window" }],
      note_count: 1,
      source_count: 1,
    });
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    fireEvent.click(screen.getByText("Preview"));
    expect((await screen.findByRole("alert")).textContent).toContain("Could not verify this preview");
    expect(screen.queryByLabelText("Revision preview")).toBeNull();
    expect(screen.getByText("1/20 windows selected")).toBeTruthy();
    expect(apply).not.toHaveBeenCalled();
  });

  it("refuses a late preview response in favor of the newest generation", async () => {
    let finishOld: ((value: unknown) => void) | undefined;
    let finishNew: ((value: unknown) => void) | undefined;
    preview
      .mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { finishNew = resolve; }));
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    const previewButton = screen.getByText("Preview");
    fireEvent.click(previewButton);
    // The fieldset supplies the global freeze. A directly dispatched event
    // models an already-queued handler from before that disabled state painted.
    previewButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => expect(preview).toHaveBeenCalledTimes(2));
    finishNew?.({ asset_id: "asset-owned", expected_predecessor: null, preview_digest: "f".repeat(64), members: [{ member_ordinal: 0, investigation_id: "new", window_id: "window-a" }], note_count: 9, source_count: 1 });
    expect(await screen.findByText("9 notes · 1 sources")).toBeTruthy();
    finishOld?.({ asset_id: "asset-owned", expected_predecessor: null, preview_digest: "0".repeat(64), members: [{ member_ordinal: 0, investigation_id: "old", window_id: "window-a" }], note_count: 2, source_count: 1 });
    await waitFor(() => expect(screen.queryByText("2 notes · 1 sources")).toBeNull());
  });

  it("isolates all refresh failures after apply and preserves the successful command and exact revision", async () => {
    const revisionId = `tnr-${"9".repeat(32)}`;
    preview.mockResolvedValue({
      asset_id: "asset-owned",
      expected_predecessor: null,
      preview_digest: "1".repeat(64),
      members: [{ member_ordinal: 0, investigation_id: "investigation-1", window_id: "window-a" }],
      note_count: 2,
      source_count: 3,
    });
    apply.mockResolvedValue({ revision_id: revisionId });
    render(<TwinNotesPanel />);
    await screen.findByRole("option", { name: "Field notes" });
    fireEvent.change(screen.getByLabelText("Twin-note asset"), { target: { value: "asset-owned" } });
    fireEvent.click(screen.getByLabelText("Add window window-a"));
    fireEvent.click(screen.getByText("Preview"));
    await screen.findByLabelText("Revision preview");
    list.mockRejectedValueOnce(new Error("list refresh failed"));
    discover.mockRejectedValueOnce(new Error("discovery refresh failed"));
    history.mockRejectedValueOnce(new Error("history refresh failed"));
    fireEvent.click(screen.getByText("Apply revision"));
    await screen.findByText(revisionId);

    expect(screen.getByLabelText("Revision preview")).toBeTruthy();
    expect(screen.getByText("1/20 windows selected")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply.mock.calls[0][0]).toMatchObject({ asset_id: "asset-owned", window_ids: ["window-a"] });
    const successfulCommand = apply.mock.calls[0][0];
    fireEvent.click(screen.getByText("Apply revision"));
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(2));
    expect(apply.mock.calls[1][0]).toEqual(successfulCommand);
  });
});
