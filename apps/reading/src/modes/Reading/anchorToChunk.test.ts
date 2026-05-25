import { describe, it, expect } from "vitest";

import { chunkProbe, findPageForChunkText, normalizeForMatch } from "./anchorToChunk";
import type { PageWindow } from "./paginate";

/**
 * Chunk-span anchoring: map a cited chunk's text to the page that contains
 * it, so a trace opens the reader at the exact span (not just the doc).
 */

function page(i: number, text: string): PageWindow {
  return { pageIndex: i, pageNumber: i + 1, text };
}

const pages: PageWindow[] = [
  page(0, "The opening of the book establishes the setting and the cast."),
  page(1, "Capital intensity rises with scale; the moat is the data, not the model."),
  page(2, "A closing reflection on what the edit reveals about the writer."),
];

describe("findPageForChunkText", () => {
  it("locates the page containing the cited chunk", () => {
    expect(findPageForChunkText(pages, "Capital intensity rises with scale")).toBe(1);
  });

  it("matches despite whitespace/case differences", () => {
    expect(findPageForChunkText(pages, "  CAPITAL   intensity\n  rises with scale  ")).toBe(1);
  });

  it("returns -1 when the chunk is not on any page", () => {
    expect(findPageForChunkText(pages, "an entirely unrelated passage about boats")).toBe(-1);
  });

  it("returns -1 for empty chunk text (no false anchor)", () => {
    expect(findPageForChunkText(pages, "   ")).toBe(-1);
  });

  it("falls back to the first sentence when the prefix straddles a boundary", () => {
    const longChunk =
      "A closing reflection on what the edit reveals about the writer. " +
      "And then text that only appears on a later, different page entirely.";
    expect(findPageForChunkText(pages, longChunk)).toBe(2);
  });
});

describe("helpers", () => {
  it("normalizeForMatch collapses whitespace + lowercases", () => {
    expect(normalizeForMatch("  A  B\nC ")).toBe("a b c");
  });
  it("chunkProbe takes a bounded normalized prefix", () => {
    expect(chunkProbe("Hello World", 5)).toBe("hello");
  });
});
