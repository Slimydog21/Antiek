/**
 * selectionCharRange.test.ts — antiek-reader SPR-06 M3 anchor offsets.
 *
 * The thread's Region char range must be BLOCK-relative (0-based, into the
 * block's own text), so it survives re-pagination. These assert the resolver
 * computes those offsets and degrades to whole-block (null) honestly when the
 * selection escapes the block.
 */
import { describe, expect, it } from "vitest";

import { charRangeInBlock, blockElementFor, resolveCharRange } from "./selectionCharRange";

function rangeOver(node: Text, start: number, end: number): Range {
  const r = document.createRange();
  r.setStart(node, start);
  r.setEnd(node, end);
  return r;
}

describe("charRangeInBlock — block-relative offsets (M3)", () => {
  it("measures char offsets into the block's own text", () => {
    const block = document.createElement("p");
    block.appendChild(document.createTextNode("Superconductors expel fields."));
    document.body.appendChild(block);
    const node = block.firstChild as Text;
    // Select "expel" (chars 16..21).
    const r = rangeOver(node, 16, 21);
    expect(charRangeInBlock(r, block)).toEqual({ charStart: 16, charEnd: 21 });
    block.remove();
  });

  it("offsets account for text in sibling nodes before the selection", () => {
    const block = document.createElement("p");
    block.appendChild(document.createTextNode("alpha "));
    const em = document.createElement("em");
    em.appendChild(document.createTextNode("beta"));
    block.appendChild(em);
    document.body.appendChild(block);
    const betaNode = em.firstChild as Text;
    const r = rangeOver(betaNode, 0, 4); // "beta", which starts at char 6
    expect(charRangeInBlock(r, block)).toEqual({ charStart: 6, charEnd: 10 });
    block.remove();
  });

  it("degrades to whole-block (null) when the range escapes the block", () => {
    const block = document.createElement("p");
    block.appendChild(document.createTextNode("inside block"));
    const outside = document.createElement("p");
    outside.appendChild(document.createTextNode("outside text"));
    document.body.append(block, outside);
    const r = rangeOver(outside.firstChild as Text, 0, 3);
    expect(charRangeInBlock(r, block)).toEqual({ charStart: null, charEnd: null });
    block.remove();
    outside.remove();
  });

  it("null block → whole-block (null), never a crash", () => {
    const orphan = document.createTextNode("x");
    expect(charRangeInBlock(rangeOver(orphan, 0, 1), null)).toEqual({ charStart: null, charEnd: null });
  });
});

describe("blockElementFor — prefers a chunk-tagged block", () => {
  it("returns the nearest data-akb-chunk-id ancestor", () => {
    const scope = document.createElement("div");
    const chunk = document.createElement("p");
    chunk.setAttribute("data-akb-chunk-id", "blk-1");
    chunk.appendChild(document.createTextNode("chunk text"));
    scope.appendChild(chunk);
    document.body.appendChild(scope);
    const r = rangeOver(chunk.firstChild as Text, 0, 5);
    expect(blockElementFor(r, scope)).toBe(chunk);
    // resolveCharRange then measures against that chunk.
    expect(resolveCharRange(r, scope)).toEqual({ charStart: 0, charEnd: 5 });
    scope.remove();
  });
});
