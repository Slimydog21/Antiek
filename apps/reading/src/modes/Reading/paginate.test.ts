import { describe, expect, it } from "vitest";

import {
  anchoredChunksForPage,
  chunksForPage,
  paginate,
  representativeChunkIdsByPage,
} from "./paginate";

describe("reader page chunk ownership", () => {
  it("keeps authoritative chunk order and removes projection-only markers", () => {
    const chunks = chunksForPage(
      [
        { chunk_id: "c2", chunk_index: 2, page_index: 0, text: "<!-- section: Page 1 -->\nLater." },
        { chunk_id: "c1", chunk_index: 1, page_index: 0, text: "## Page 1\n\nFirst." },
        { chunk_id: "c3", chunk_index: 3, page_index: 1, text: "## Page 2\nOther." },
      ],
      0,
    );
    expect(chunks.map((chunk) => chunk.chunk_id)).toEqual(["c1", "c2"]);
    expect(chunks.map((chunk) => chunk.text)).toEqual(["First.", "Later."]);
  });

  it("does not guess page ownership for an unresolved chunk", () => {
    expect(
      chunksForPage(
        [{ chunk_id: "c0", chunk_index: 0, page_index: null, text: "Unpaged." }],
        0,
      ),
    ).toEqual([]);
    expect(paginate("Unpaged.")).toHaveLength(1);
  });

  it("falls back to unanchored prose when resolved chunks omit page content", () => {
    expect(
      anchoredChunksForPage(
        [{ chunk_id: "c1", chunk_index: 0, page_index: 0, text: "First half." }],
        0,
        "First half. Missing second half.",
      ),
    ).toEqual([]);
  });

  it("anchors every region when ordered chunks reconstruct the whole page", () => {
    expect(
      anchoredChunksForPage(
        [
          { chunk_id: "c1", chunk_index: 0, page_index: 0, text: "## Page 1\nFirst." },
          { chunk_id: "c2", chunk_index: 1, page_index: 0, text: "<!-- section: Page 1 -->\nSecond." },
        ],
        0,
        "First.\n\nSecond.",
      ).map((chunk) => chunk.chunk_id),
    ).toEqual(["c1", "c2"]);
  });

  it("assigns dwell identity only to fully reconstructed pages", () => {
    const pages = paginate("## Page 1\nComplete.\n## Page 2\nVisible but incomplete.");
    const representatives = representativeChunkIdsByPage(
      [
        { chunk_id: "c1", chunk_index: 0, page_index: 0, text: "## Page 1\nComplete." },
        { chunk_id: "c2", chunk_index: 1, page_index: 1, text: "## Page 2\nVisible" },
      ],
      pages,
    );
    expect(representatives.get(0)).toBe("c1");
    expect(representatives.has(1)).toBe(false);
  });
});
