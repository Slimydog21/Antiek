import { describe, expect, it } from "vitest";

import { buildReaderTarget, decodeRegion, encodeRegion } from "./openDocument";

describe("openDocument resolver target", () => {
  it("normalizes document, chunk, and highlight ids before building the reader URL", () => {
    const target = buildReaderTarget(" doc source/1 ", {
      page: 3,
      chunkId: " chunk 7 ",
      highlight: {
        document_id: " doc source/1 ",
        block_id: " chunk 7 ",
        char_start: 12,
        char_end: 18,
      },
      origin: {
        documentId: " origin doc ",
        page: 1,
        title: "  Source note  ",
      },
    });

    expect(target.path).toBe("/read/doc%20source%2F1");
    const params = new URLSearchParams(target.search);
    expect(params.get("page")).toBe("3");
    expect(params.get("chunk")).toBe("chunk 7");
    expect(params.get("hl")).toBe("doc%20source%2F1:chunk%207:12-18");
    expect(params.get("from")).toBe("origin doc");
    expect(params.get("fromPage")).toBe("1");
    expect(params.get("fromTitle")).toBe("Source note");
  });

  it("drops blank optional handles instead of minting empty locators", () => {
    const target = buildReaderTarget(" doc-1 ", {
      chunkId: " ",
      highlight: {
        document_id: " ",
        block_id: "chunk-7",
        char_start: 1,
        char_end: 2,
      },
      page: Number.POSITIVE_INFINITY,
      origin: {
        documentId: " ",
        page: -1,
        title: " ",
      },
    });

    expect(target).toEqual({ path: "/read/doc-1", search: "" });
  });

  it("round-trips encoded regions with trimmed ids and rejects blank decoded ids", () => {
    const encoded = encodeRegion({
      document_id: " doc:1 ",
      block_id: " block:2 ",
      char_start: 0,
      char_end: 10,
    });

    expect(encoded).toBe("doc%3A1:block%3A2:0-10");
    expect(decodeRegion(encoded)).toEqual({
      document_id: "doc:1",
      block_id: "block:2",
      char_start: 0,
      char_end: 10,
    });
    expect(decodeRegion("%20:chunk-1")).toBeNull();
  });
});
