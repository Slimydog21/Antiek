import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ChunkResponse } from "../../lib/api";
import ChunkModal, { sourcePageFromSectionPath } from "./ChunkModal";

const { getChunkMock, openDocumentMock } = vi.hoisted(() => ({
  getChunkMock: vi.fn(),
  openDocumentMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getChunk: getChunkMock,
}));

vi.mock("../../lib/openDocument", async (orig) => ({
  ...(await orig<typeof import("../../lib/openDocument")>()),
  useOpenDocument: () => openDocumentMock,
}));

function chunk(over: Partial<ChunkResponse> = {}): ChunkResponse {
  return {
    chunk_id: "c1",
    text: "evidence",
    section_path: "Page 12",
    token_count: 8,
    document_id: "doc-1",
    document_title: "Source Book",
    source_tier: 2,
    servable: true,
    servability: null,
    ...over,
  };
}

afterEach(() => {
  cleanup();
  getChunkMock.mockReset();
  openDocumentMock.mockReset();
});

describe("ChunkModal — open in document locator", () => {
  it("parses source page labels without treating timestamps as pages", () => {
    expect(sourcePageFromSectionPath("Page 17")).toBe(17);
    expect(sourcePageFromSectionPath("Page 17 · Section 3.2")).toBe(17);
    expect(sourcePageFromSectionPath("p.12")).toBe(12);
    expect(sourcePageFromSectionPath("p 12")).toBe(12);
    expect(sourcePageFromSectionPath("Timestamp 00:17")).toBeNull();
    expect(sourcePageFromSectionPath(null)).toBeNull();
  });

  it("opens p.N chunks on the matching zero-based reader page", async () => {
    getChunkMock.mockResolvedValue(chunk({ section_path: "p.12" }));
    render(<ChunkModal chunkId="c1" onClose={() => {}} />);

    await screen.findByText("Source Book");
    const open = await screen.findByRole("button", { name: /open at page 12/i });
    await userEvent.click(open);

    await waitFor(() =>
      expect(openDocumentMock).toHaveBeenCalledWith("doc-1", {
        page: 11,
        chunkId: "c1",
      }),
    );
  });
});
