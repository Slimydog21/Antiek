import { describe, expect, it } from "vitest";

import { resolveSynthesisSelectionProvenance } from "./HighlightToolbar";

function claim(id: string, chunks: string[], text: string): HTMLSpanElement {
  const span = document.createElement("span");
  span.dataset.claimId = id;
  span.dataset.citedChunkIds = JSON.stringify(chunks);
  span.append(document.createTextNode(text));
  return span;
}

describe("resolveSynthesisSelectionProvenance", () => {
  it("returns the exact ordered citation envelope only within one claim", () => {
    const span = claim("7", ["chunk-a", "chunk-b"], "A grounded synthesis claim");
    document.body.append(span);
    const range = document.createRange();
    range.setStart(span.firstChild!, 2);
    range.setEnd(span.firstChild!, 10);
    expect(resolveSynthesisSelectionProvenance(range)).toEqual({
      claimId: "7", chunkId: "chunk-a", chunkIds: ["chunk-a", "chunk-b"],
    });
    span.remove();
  });

  it("does not borrow evidence for cross-claim or uncited prose", () => {
    const root = document.createElement("div");
    const first = claim("1", ["chunk-a"], "First claim");
    const second = claim("2", ["chunk-b"], "Second claim");
    const prose = document.createTextNode(" uncited thesis ");
    root.append(first, prose, second);
    document.body.append(root);
    const cross = document.createRange();
    cross.setStart(first.firstChild!, 0);
    cross.setEnd(second.firstChild!, 4);
    expect(resolveSynthesisSelectionProvenance(cross)).toEqual({});
    const uncited = document.createRange();
    uncited.selectNodeContents(prose);
    expect(resolveSynthesisSelectionProvenance(uncited)).toEqual({});
    root.remove();
  });

  it("fails closed for empty, duplicate, or malformed citation metadata", () => {
    for (const encoded of ["[]", '["dup","dup"]', "not-json"]) {
      const span = claim("3", ["placeholder"], "Claim");
      span.dataset.citedChunkIds = encoded;
      document.body.append(span);
      const range = document.createRange();
      range.selectNodeContents(span);
      expect(resolveSynthesisSelectionProvenance(range)).toEqual({});
      span.remove();
    }
  });
});
