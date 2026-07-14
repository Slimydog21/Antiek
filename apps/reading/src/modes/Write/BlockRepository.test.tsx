import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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

  it("carries a claim's semantic kind through native drag", async () => {
    render(<BlockRepository onAdd={vi.fn()} />);
    const block = await screen.findByRole("button", { name: /capital intensity/i });
    const setData = vi.fn();
    fireEvent.dragStart(block, { dataTransfer: { setData, effectAllowed: "none" } });
    expect(setData).toHaveBeenCalledWith(
      "application/x-antiek-block",
      expect.stringContaining('"block_kind":"claim"'),
    );
  });
});
