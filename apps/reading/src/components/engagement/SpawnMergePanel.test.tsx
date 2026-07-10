import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpawnMergePanel } from "./SpawnMergePanel";

const mergeSpawnOutputs = vi.fn();
const openWindow = vi.fn(
  (_kind: unknown, _payload: unknown, _options: unknown) => "win:merge:draft_1",
);

vi.mock("../../api/engagement", () => ({
  mergeSpawnOutputs: (body: unknown) => mergeSpawnOutputs(body),
}));

vi.mock("../windows/openWindow", () => ({
  openWindow: (kind: unknown, payload: unknown, options: unknown) =>
    openWindow(kind, payload, options),
}));

describe("SpawnMergePanel residual ci", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    mergeSpawnOutputs.mockReset();
    openWindow.mockClear();
  });

  it("creates draft combined from single spawn", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_book-1_abc",
      source_spawn_ids: ["spn_1"],
      sections_merged: 2,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft-combined document"],
      html: "<p>Draft merge HTML</p>",
    });

    const onMerged = vi.fn();
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        onMerged={onMerged}
      />,
    );
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-auto-open-draft"),
    ).toBe("true");
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalledWith({
        parent_asset_id: "book-1",
        spawn_ids: ["spn_1"],
        mode: "draft_combined",
        include_html: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-result").textContent).toMatch(
        /draft_combined/,
      );
    });
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("spawn-merge-html").innerHTML).toMatch(/Draft merge/);
    await waitFor(() => {
      expect(onMerged).toHaveBeenCalled();
    });
    expect(onMerged.mock.calls[0][0].document_id).toBe("draft_book-1_abc");
    expect(onMerged.mock.calls[0][0].view_format).toBe("html");
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "draft_book-1_abc",
          view_format: "html",
          html: "<p>Draft merge HTML</p>",
          source: "spawn_merge_panel",
        }),
        expect.objectContaining({
          id: "win:merge:draft_book-1_abc",
          mode: "floating",
        }),
      );
    });
    expect(screen.getByTestId("spawn-merge-auto-open-window").textContent).toMatch(
      /win:merge:draft_1/,
    );
  });

  it("does not auto-open draft when autoOpenDraft is false", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_manual",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>Manual open</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-auto-open-draft"),
    ).toBe("false");
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-window")).toBeTruthy();
    });
    expect(openWindow).not.toHaveBeenCalled();
    expect(screen.queryByTestId("spawn-merge-auto-open-window")).toBeNull();
  });

  it("opens merged HTML in full working-region window (ev)", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_full",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>Full open</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-full")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("spawn-merge-open-full"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "draft_full",
        view_format: "html",
      }),
      expect.objectContaining({
        id: "win:merge:draft_full:full",
        mode: "full",
      }),
    );
  });

  it("merges into parent without auto-open; manual open still works", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "into_parent",
      parent_asset_id: "book-1",
      document_id: "book-1",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: false,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Merged into parent"],
      html: "<p>Parent merge HTML</p>",
    });

    render(
      <SpawnMergePanel spawnId="spn_1" parentAssetId="book-1" />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-parent"));
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalledWith({
        parent_asset_id: "book-1",
        spawn_ids: ["spn_1"],
        mode: "into_parent",
        include_html: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-window")).toBeTruthy();
    });
    expect(openWindow).not.toHaveBeenCalled();
    expect(screen.queryByTestId("spawn-merge-auto-open-window")).toBeNull();
    fireEvent.click(screen.getByTestId("spawn-merge-open-window"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "book-1",
        view_format: "html",
      }),
      expect.objectContaining({ mode: "floating" }),
    );
  });

  it("refuses non-html view_format", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "x",
      source_spawn_ids: ["spn_1"],
      sections_merged: 0,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "pdf",
      product_panel: "engagement_merge",
      source: "test",
      notes: [],
      html: "%PDF",
    });
    render(
      <SpawnMergePanel spawnId="spn_1" parentAssetId="book-1" />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/html/i);
    });
  });
});
