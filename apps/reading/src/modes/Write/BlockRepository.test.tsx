import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import { repositoryBlockKind } from "./repositoryData";
import type { RepositoryHit } from "./writeApi";

/**
 * BlockRepository.test — the tap-to-add picker (Product Depth SPR-07 M1).
 *
 * Load-bearing claims, mechanically checked:
 *  - a block is added by a TAP (onAdd fires with the hit) — not by pasting an
 *    id; there is no "attach by id" form on this surface;
 *  - a block renders its TEXT + provenance, never its node_id (the no-UUID
 *    gate) — the rendered DOM carries no id-shaped string.
 */

const { searchRepositoryMock, listFoldersMock } = vi.hoisted(() => ({
  searchRepositoryMock: vi.fn(),
  listFoldersMock: vi.fn(),
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  searchRepository: searchRepositoryMock,
  listFolders: listFoldersMock,
}));

import BlockRepository from "./BlockRepository";

const NODE_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"; // a 32-hex id — must NOT render
const HIT: RepositoryHit = {
  node_id: NODE_ID,
  label: "Capital intensity rises with scale",
  node_type: "claim",
  source_tier: 2,
  document_id: "doc-1",
  document_title: "Source Book",
  score: 0.9,
};

beforeEach(() => {
  searchRepositoryMock.mockReset().mockResolvedValue([HIT]);
  listFoldersMock.mockReset().mockResolvedValue([]);
});
afterEach(cleanup);

describe("BlockRepository — tap-to-add, no id", () => {
  it("maps repository node types to graph-backed write block kinds", () => {
    expect(repositoryBlockKind("insight")).toBe("insight");
    expect(repositoryBlockKind("open_question")).toBe("open_question");
    expect(repositoryBlockKind("claim")).toBe("claim");
    expect(repositoryBlockKind("operator_note")).toBe("claim");
    expect(repositoryBlockKind(" future_node ")).toBe("claim");
  });

  it("adds a block by TAP (onAdd fires with the hit), not by pasting an id", async () => {
    const onAdd = vi.fn();
    render(<BlockRepository onAdd={onAdd} />);

    const block = await screen.findByText("Capital intensity rises with scale");
    await userEvent.click(block);
    expect(onAdd).toHaveBeenCalledWith(HIT);
  });

  it("has no 'attach by id' affordance and renders no UUID", async () => {
    const { container } = render(<BlockRepository onAdd={vi.fn()} />);
    await screen.findByText("Capital intensity rises with scale");

    // No attach-by-id path on the surface (the CreationStudio dead-end).
    expect(screen.queryByText(/attach by id/i)).toBeNull();
    // The block's text + provenance show; its node_id never does.
    expect(screen.getByText(/Source Book/)).toBeTruthy();
    expect(container.textContent ?? "").not.toContain(NODE_ID);
    // No 32-hex id-shaped string anywhere in the rendered DOM.
    expect((container.textContent ?? "").match(/\b[0-9a-f]{32,40}\b/i)).toBeNull();
  });

  it("shows an honest empty state when the shelf has no blocks (no fabrication)", async () => {
    searchRepositoryMock.mockResolvedValue([]);
    render(<BlockRepository onAdd={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/No blocks/i)).toBeTruthy(),
    );
  });

  it("updates the search folder when the host folder prop changes", async () => {
    const rendered = render(
      <BlockRepository onAdd={vi.fn()} initialFolderId="folder-a" />,
    );
    await waitFor(() =>
      expect(searchRepositoryMock).toHaveBeenCalledWith(
        expect.objectContaining({ folderId: "folder-a" }),
      ),
    );

    rendered.rerender(
      <BlockRepository onAdd={vi.fn()} initialFolderId="folder-b" />,
    );

    await waitFor(() =>
      expect(searchRepositoryMock).toHaveBeenCalledWith(
        expect.objectContaining({ folderId: "folder-b" }),
      ),
    );
  });

  it("drops malformed folders and hits before rendering or selecting", async () => {
    const onAdd = vi.fn();
    listFoldersMock.mockResolvedValue([
      { folder_id: " folder-1 ", name: "  Saved insights  ", member_count: "2" },
      { folder_id: " ", name: "Invisible folder", member_count: 1 },
      { folder_id: "folder-2", name: "", member_count: 1 },
    ]);
    searchRepositoryMock.mockResolvedValue([
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

    render(<BlockRepository onAdd={onAdd} />);
    await userEvent.click(await screen.findByText("Useful claim"));

    expect(await screen.findByText("Saved insights · 2")).toBeTruthy();
    expect(screen.getByText("Source document · tier 2")).toBeTruthy();
    expect(screen.queryByText("Invisible folder")).toBeNull();
    expect(screen.queryByText("Invisible hit")).toBeNull();
    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        node_id: "node-1",
        label: "Useful claim",
        document_title: "Source document",
        source_tier: 2,
      }),
    );
  });

  it("serializes sanitized drag payloads without flattening claim nodes to insights", async () => {
    searchRepositoryMock.mockResolvedValue([
      {
        node_id: " node-1 ",
        label: "  Useful claim  ",
        node_type: "claim",
        source_tier: null,
        document_id: null,
        document_title: null,
        score: 1,
      },
    ]);
    render(<BlockRepository onAdd={vi.fn()} />);
    const row = await screen.findByTitle("Tap to add to the outline (or drag)");
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
});
