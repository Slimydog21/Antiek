import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpawnMergePanel } from "./SpawnMergePanel";

const mergeSpawnOutputs = vi.fn();
const seedTwinNotes = vi.fn();
const openWindow = vi.fn(() => "win:merge:draft_1");

vi.mock("../../api/engagement", () => ({
  mergeSpawnOutputs: (...args: unknown[]) => mergeSpawnOutputs(...args),
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
}));

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

describe("SpawnMergePanel residual ci", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    mergeSpawnOutputs.mockReset();
    seedTwinNotes.mockReset();
    seedTwinNotes.mockResolvedValue({
      asset_id: "draft_book-1_abc",
      seeded: true,
      view_format: "html",
      notes: [],
      insight_count: 1,
      question_count: 1,
    });
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

    render(
      <SpawnMergePanel spawnId="spn_1" parentAssetId="book-1" />,
    );
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
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_book-1_abc",
          force_offline: true,
          source_spawn_id: "spn_1",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-result").textContent).toMatch(
        /draft_combined|Twin notes seeded/,
      );
    });
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("spawn-merge-html").innerHTML).toMatch(/Draft merge/);
  });

  it("merges into parent and opens HTML window", async () => {
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
