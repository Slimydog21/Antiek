import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: apiFetchMock,
}));

import { corpusSearch } from "./corpusSearch";

beforeEach(() => {
  apiFetchMock.mockReset();
});

describe("corpusSearch api boundary", () => {
  it("does not burn a request for empty queries", async () => {
    await expect(corpusSearch("   ")).resolves.toEqual({
      query: "   ",
      hits: [],
      count: 0,
    });

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("sanitizes hits before search results can open the reader", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          query: "  preserved backend query  ",
          hits: [
            {
              chunk_id: " chunk-1 ",
              document_id: " doc-1 ",
              document_title: "  Title One  ",
              page_index: 4,
              page_resolved: true,
              snippet: "  passage one  ",
              similarity: 0.91,
            },
            {
              chunk_id: "chunk-unresolved",
              document_id: "doc-2",
              document_title: "",
              page_index: "4",
              page_resolved: true,
              snippet: "unresolved passage",
              similarity: "close",
            },
            {
              chunk_id: " ",
              document_id: "doc-3",
              page_index: 2,
              page_resolved: true,
              snippet: "missing chunk id",
              similarity: 0.7,
            },
          ],
          count: "three",
        }),
        { status: 200 },
      ),
    );

    await expect(corpusSearch("quantum mechanics")).resolves.toEqual({
      query: "  preserved backend query  ",
      hits: [
        {
          chunk_id: "chunk-1",
          document_id: "doc-1",
          document_title: "Title One",
          page_index: 4,
          page_resolved: true,
          snippet: "passage one",
          similarity: 0.91,
        },
        {
          chunk_id: "chunk-unresolved",
          document_id: "doc-2",
          document_title: null,
          page_index: null,
          page_resolved: false,
          snippet: "unresolved passage",
          similarity: 0,
        },
      ],
      count: 2,
    });
  });

  it("rejects malformed top-level responses instead of trusting casts", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(["not", "an", "object"]), { status: 200 }),
    );

    await expect(corpusSearch("anything")).rejects.toThrow(
      "Malformed corpus search response.",
    );
  });
});
