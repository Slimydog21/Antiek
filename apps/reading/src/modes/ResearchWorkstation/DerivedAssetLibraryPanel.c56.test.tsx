import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DerivedAssetLibraryPanel, { derivedAssetPreviewUrl } from "./DerivedAssetLibraryPanel";

const mocks = vi.hoisted(() => ({ discover: vi.fn(), history: vi.fn(), restore: vi.fn() }));
vi.mock("../../api/research", () => ({
  discoverDerivedAssets: (...args: unknown[]) => mocks.discover(...args),
  getDerivedAssetHistory: (...args: unknown[]) => mocks.history(...args),
  restoreDerivedAsset: (...args: unknown[]) => mocks.restore(...args),
}));

const assetId = `ast_${"a".repeat(32)}`;
const currentId = `rev_${"b".repeat(32)}`;
const oldId = `rev_${"c".repeat(32)}`;
const restoredId = `rev_${"d".repeat(32)}`;
const currentHash = "1".repeat(64);
const oldHash = "2".repeat(64);
const current = {
  revision_id: currentId, content_sha256: currentHash, generation: 2, member_count: 2,
  preview_url: `/research/derived-assets/assets/${assetId}/current/frame-preview`,
};
const summary = { derived_asset_id: assetId, title: "Flight analysis", asset_kind: "analysis" as const, current, revision_count: 2 };
const oldRevision = {
  revision_id: oldId, operation_kind: "create" as const, content_sha256: oldHash,
  parent_revision_id: null, restored_from_revision_id: null, member_count: 1,
  is_current: false,
  preview_url: `/research/derived-assets/assets/${assetId}/revisions/${oldId}/frame-preview`,
};
const history = {
  ...summary,
  revisions: [{
    revision_id: currentId, operation_kind: "revise" as const, content_sha256: currentHash,
    parent_revision_id: oldId, restored_from_revision_id: null, member_count: 2,
    is_current: true,
    preview_url: `/research/derived-assets/assets/${assetId}/revisions/${currentId}/frame-preview`,
  }, oldRevision],
};

describe("Cycle 56 derived asset library", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.discover.mockResolvedValue({ assets: [summary], limits: { assets: 200, revisions_per_asset: 400 } });
    mocks.history.mockResolvedValue(history);
  });

  it("compares exact current and historical HTML and retries one restore command", async () => {
    const refreshed = {
      ...history,
      current: { ...current, revision_id: restoredId, content_sha256: oldHash, generation: 3 },
      revision_count: 3,
      revisions: [{
        ...oldRevision, revision_id: restoredId, operation_kind: "restore" as const,
        parent_revision_id: currentId, restored_from_revision_id: oldId, is_current: true,
      }, { ...history.revisions[0], is_current: false }, oldRevision],
    };
    mocks.history.mockResolvedValueOnce(history).mockResolvedValueOnce(refreshed);
    mocks.restore.mockRejectedValueOnce(new Error("unknown outcome")).mockImplementationOnce(
      (_asset: string, request: { operation_id: string }) => Promise.resolve({
        operation_id: request.operation_id, derived_asset_id: assetId, revision_id: restoredId,
        content_sha256: oldHash, generation: 3, replayed: true,
      }),
    );
    const pending = vi.fn();
    render(<DerivedAssetLibraryPanel disabled={false} onPendingChange={pending} />);
    fireEvent.click(screen.getByText("Browse derived assets"));
    await screen.findByRole("option", { name: /Flight analysis/ });
    fireEvent.change(screen.getByLabelText("Derived asset"), { target: { value: assetId } });
    await screen.findByRole("option", { name: new RegExp(oldId) });
    fireEvent.change(screen.getByLabelText("Historical derived asset revision"), { target: { value: oldId } });
    expect(screen.getByTitle("Current derived asset HTML").getAttribute("sandbox")).toBe("");
    expect(screen.getByTitle("Historical derived asset HTML").getAttribute("sandbox")).toBe("");
    fireEvent.click(screen.getByText("Restore as new revision"));
    await screen.findByRole("alert");
    const first = mocks.restore.mock.calls[0];
    fireEvent.click(screen.getByText("Restore as new revision"));
    expect(await screen.findByText(/Restored as revision/)).toBeTruthy();
    expect(mocks.restore.mock.calls[1]).toEqual(first);
    expect(first[1]).toMatchObject({
      selected_revision_id: oldId, expected_revision_id: currentId,
      expected_content_sha256: currentHash, expected_generation: 2,
    });
    expect(pending).toHaveBeenCalledWith(true);
    expect(pending).toHaveBeenLastCalledWith(false);
  });

  it("refuses a late history response after asset selection changes", async () => {
    const secondAsset = `ast_${"e".repeat(32)}`;
    mocks.discover.mockResolvedValue({
      assets: [summary, { ...summary, derived_asset_id: secondAsset, title: "Second" }],
      limits: { assets: 200, revisions_per_asset: 400 },
    });
    let settleFirst: ((value: unknown) => void) | undefined;
    mocks.history
      .mockReturnValueOnce(new Promise((resolve) => { settleFirst = resolve; }))
      .mockResolvedValueOnce({ ...history, derived_asset_id: secondAsset, title: "Second" });
    render(<DerivedAssetLibraryPanel disabled={false} onPendingChange={vi.fn()} />);
    fireEvent.click(screen.getByText("Browse derived assets"));
    await screen.findByRole("option", { name: /Flight analysis/ });
    const select = screen.getByLabelText("Derived asset");
    fireEvent.change(select, { target: { value: assetId } });
    fireEvent.change(select, { target: { value: secondAsset } });
    await screen.findByLabelText("Historical derived asset revision");
    settleFirst?.(history);
    await waitFor(() => expect(screen.getByText("Second · analysis · 2 revisions")).toBeTruthy());
    expect((select as HTMLSelectElement).value).toBe(secondAsset);
  });

  it("accepts only exact same-origin derived asset frame routes", () => {
    expect(derivedAssetPreviewUrl(current.preview_url)).toContain(assetId);
    expect(derivedAssetPreviewUrl(oldRevision.preview_url)).toContain(oldId);
    expect(() => derivedAssetPreviewUrl("https://evil.example/frame-preview")).toThrow();
    expect(() => derivedAssetPreviewUrl(`/research/derived-assets/assets/${assetId}/revisions`)).toThrow();
  });

  it("invalidates history and restore authority before a failing refresh", async () => {
    render(<DerivedAssetLibraryPanel disabled={false} onPendingChange={vi.fn()} />);
    fireEvent.click(screen.getByText("Browse derived assets"));
    await screen.findByRole("option", { name: /Flight analysis/ });
    fireEvent.change(screen.getByLabelText("Derived asset"), { target: { value: assetId } });
    await screen.findByRole("option", { name: new RegExp(oldId) });
    fireEvent.change(screen.getByLabelText("Historical derived asset revision"), {
      target: { value: oldId },
    });
    expect(screen.getByText("Restore as new revision")).toBeTruthy();
    mocks.discover.mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByLabelText("Refresh derived assets"));
    expect(screen.queryByTitle("Current derived asset HTML")).toBeNull();
    expect(screen.queryByText("Restore as new revision")).toBeNull();
    await screen.findByRole("alert");
  });
});
