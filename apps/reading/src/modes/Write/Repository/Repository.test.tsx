import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DRAG_MIME } from "../../CreationStudio/BlockPalette";
import Repository from "./Repository";

const { listFoldersMock, searchRepositoryMock } = vi.hoisted(() => ({
  listFoldersMock: vi.fn(),
  searchRepositoryMock: vi.fn(),
}));

vi.mock("../writeApi", async (orig) => {
  const actual = await orig<typeof import("../writeApi")>();
  return {
    ...actual,
    listFolders: listFoldersMock,
    searchRepository: searchRepositoryMock,
  };
});

beforeEach(() => {
  listFoldersMock.mockReset().mockResolvedValue([
    { folder_id: " folder-1 ", name: "  Saved insights  ", member_count: "2" },
    { folder_id: " ", name: "Invisible folder", member_count: 1 },
    { folder_id: "folder-2", name: "", member_count: 1 },
  ]);
  searchRepositoryMock.mockReset().mockResolvedValue([
    {
      node_id: " node-1 ",
      label: "  Useful claim  ",
      node_type: "claim",
      source_tier: "2",
      document_id: "doc-1",
      document_title: "  Source document  ",
      score: 1,
    },
    {
      node_id: " ",
      label: "Invisible hit",
      node_type: "claim",
      source_tier: 1,
      document_id: null,
      document_title: null,
      score: 1,
    },
  ]);
});

afterEach(() => cleanup());

describe("Write Repository", () => {
  it("sanitizes malformed folders and repository hits", async () => {
    render(<Repository />);

    expect(await screen.findByText("Saved insights")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(await screen.findByText("Useful claim")).toBeTruthy();
    expect(screen.getByText("Source document · tier 2")).toBeTruthy();
    expect(screen.queryByText("Invisible folder")).toBeNull();
    expect(screen.queryByText("Invisible hit")).toBeNull();
  });

  it("updates the search folder when the host folder prop changes", async () => {
    const rendered = render(<Repository initialFolderId="folder-a" />);
    await waitFor(() =>
      expect(searchRepositoryMock).toHaveBeenCalledWith(
        expect.objectContaining({ folderId: "folder-a" }),
      ),
    );

    rendered.rerender(<Repository initialFolderId="folder-b" />);

    await waitFor(() =>
      expect(searchRepositoryMock).toHaveBeenCalledWith(
        expect.objectContaining({ folderId: "folder-b" }),
      ),
    );
  });

  it("serializes sanitized drag payloads without flattening claim nodes to insights", async () => {
    render(<Repository />);
    const row = await screen.findByTitle("Drag into the outline");
    const data = new Map<string, string>();

    fireEvent.dragStart(row, {
      dataTransfer: {
        setData: (type: string, value: string) => data.set(type, value),
        effectAllowed: "",
      },
    });

    expect(JSON.parse(data.get(DRAG_MIME) ?? "{}")).toEqual({
      from: "palette",
      block_kind: "claim",
      block_id: "node-1",
      label: "Useful claim",
    });
  });

  it("shows the empty state when all hits are malformed", async () => {
    searchRepositoryMock.mockResolvedValue([
      {
        node_id: "",
        label: "Invisible hit",
        node_type: "claim",
        source_tier: 1,
        document_id: null,
        document_title: null,
        score: 1,
      },
    ]);

    render(<Repository />);

    await waitFor(() => expect(screen.getByText(/No blocks/)).toBeTruthy());
    expect(screen.queryByText("Invisible hit")).toBeNull();
  });
});
