import { describe, it, expect } from "vitest";

import type { EditorBlock } from "./locator";
import {
  locatorForBlock,
  resolveLocator,
  splitIntoSentences,
  toBackendLocator,
  newBlockId,
} from "./locator";

/**
 * Locator stability is "the case that bites" (SPR-04 rigor #3): style
 * prompts and edit capture both anchor here, so a locator must survive
 * edits elsewhere and edits within the block, and miss cleanly when its
 * block is deleted.
 */

function prose(blockId: string, text: string): EditorBlock {
  return { blockId, text, kind: "prose" };
}

describe("locator stability", () => {
  it("resolves by blockId even after blocks shift position", () => {
    const before = [prose("a", "first"), prose("b", "second")];
    const loc = locatorForBlock("sec-1", before, "b")!;
    expect(loc.paragraphIndex).toBe(1);

    // Insert a block before the target — its index shifts to 2.
    const after = [prose("x", "new"), prose("a", "first"), prose("b", "second")];
    const resolved = resolveLocator(after, loc);
    expect(resolved).not.toBeNull();
    expect(resolved!.block.blockId).toBe("b"); // still the right block
    expect(resolved!.index).toBe(2); // at its new position
    expect(resolved!.via).toBe("blockId"); // resolved stably, not by ordinal
  });

  it("resolves by blockId after a within-block text edit", () => {
    const loc = locatorForBlock("sec-1", [prose("a", "v1")], "a")!;
    const after = [prose("a", "v1 edited substantially")];
    const resolved = resolveLocator(after, loc);
    expect(resolved!.via).toBe("blockId");
    expect(resolved!.block.text).toBe("v1 edited substantially");
  });

  it("misses cleanly when the block was deleted", () => {
    const loc = locatorForBlock("sec-1", [prose("a", "x"), prose("b", "y")], "b")!;
    // 'b' deleted; only 'a' remains. paragraphIndex 1 is now out of range.
    const resolved = resolveLocator([prose("a", "x")], loc);
    expect(resolved).toBeNull(); // surfaced, not a throw
  });

  it("falls back to paragraphIndex when blockId is gone but a block exists there", () => {
    const loc = locatorForBlock("sec-1", [prose("a", "x"), prose("b", "y")], "a")!;
    // 'a' replaced by a fresh-id block at the same position (e.g. full retype).
    const resolved = resolveLocator([prose("a2", "rewritten"), prose("b", "y")], loc);
    expect(resolved).not.toBeNull();
    expect(resolved!.via).toBe("paragraphIndex");
    expect(resolved!.index).toBe(0);
  });
});

describe("sentence splitting", () => {
  it("splits on sentence boundaries", () => {
    expect(splitIntoSentences("One. Two! Three?")).toEqual(["One.", "Two!", "Three?"]);
  });
  it("drops empties", () => {
    expect(splitIntoSentences("  Solo sentence  ")).toEqual(["Solo sentence"]);
  });
  it("handles multiple whitespace between sentences", () => {
    expect(splitIntoSentences("One.   Two!")).toEqual(["One.", "Two!"]);
  });
  it("keeps the tail sentence when no trailing whitespace", () => {
    expect(splitIntoSentences("One. Two")).toEqual(["One.", "Two"]);
  });
});

describe("sentence splitting — abbreviations", () => {
  it("does not split on common honorific abbreviations", () => {
    expect(splitIntoSentences("Dr. Smith arrived. He spoke.")).toEqual([
      "Dr. Smith arrived.",
      "He spoke.",
    ]);
    expect(splitIntoSentences("Mr. and Mrs. Jones went home.")).toEqual([
      "Mr. and Mrs. Jones went home.",
    ]);
    expect(splitIntoSentences("Prof. Lin published it.")).toEqual([
      "Prof. Lin published it.",
    ]);
  });
  it("does not split on institutional abbreviations", () => {
    expect(splitIntoSentences("Acme Inc. reported earnings. Revenue rose.")).toEqual([
      "Acme Inc. reported earnings.",
      "Revenue rose.",
    ]);
    expect(splitIntoSentences("Smith Jr. wrote the paper.")).toEqual([
      "Smith Jr. wrote the paper.",
    ]);
  });
  it("treats ambiguous St./Ave./Blvd. as sentence boundaries", () => {
    expect(splitIntoSentences("Meet at 5th St. by the park.")).toEqual([
      "Meet at 5th St.",
      "by the park.",
    ]);
  });
  it("does not split on i.e./e.g./etc.", () => {
    expect(splitIntoSentences("Use the fast path, i.e. the shortcut.")).toEqual([
      "Use the fast path, i.e. the shortcut.",
    ]);
    expect(splitIntoSentences("See mammals, e.g. whales.")).toEqual([
      "See mammals, e.g. whales.",
    ]);
    expect(splitIntoSentences("And so on, etc. Nothing more.")).toEqual([
      "And so on, etc.",
      "Nothing more.",
    ]);
  });
  it("does not split on dotted initialisms", () => {
    expect(splitIntoSentences("U.S. GDP rose. Markets noticed.")).toEqual([
      "U.S. GDP rose.",
      "Markets noticed.",
    ]);
  });
  it("handles abbreviations at the end of a sentence (no next word)", () => {
    expect(splitIntoSentences("Talk to Dr.")).toEqual(["Talk to Dr."]);
    expect(splitIntoSentences("Published by Acme Inc.")).toEqual(["Published by Acme Inc."]);
  });
});

describe("sentence splitting — decimal numbers", () => {
  it("does not split on decimal numbers", () => {
    expect(splitIntoSentences("The value is 3.14 percent. Next sentence.")).toEqual([
      "The value is 3.14 percent.",
      "Next sentence.",
    ]);
    expect(splitIntoSentences("Price was €2.50 each. Then it changed.")).toEqual([
      "Price was €2.50 each.",
      "Then it changed.",
    ]);
  });
  it("handles decimals at the end of a sentence", () => {
    expect(splitIntoSentences("It measured 3.14.")).toEqual(["It measured 3.14."]);
  });
});

describe("sentence splitting — mixed real-world prose", () => {
  it("handles a paragraph with abbreviations, decimals, and genuine boundaries", () => {
    const text =
      "Dr. Smith arrived at 3.14 PM. He met Mrs. Jones at 5th St. She said, \"Hi!\" Then they left.";
    expect(splitIntoSentences(text)).toEqual([
      "Dr. Smith arrived at 3.14 PM.",
      "He met Mrs. Jones at 5th St.",
      "She said, \"Hi!\"",
      "Then they left.",
    ]);
  });
  it("handles a paragraph with i.e./e.g. and genuine boundaries", () => {
    const text = "Use the fast path, i.e. the shortcut. Then verify, e.g. run tests. Done.";
    expect(splitIntoSentences(text)).toEqual([
      "Use the fast path, i.e. the shortcut.",
      "Then verify, e.g. run tests.",
      "Done.",
    ]);
  });
});

describe("backend locator mapping", () => {
  it("maps a lego block to outline_block_id", () => {
    const lego: EditorBlock = {
      blockId: "blk-1", text: "insight text", kind: "lego",
      nodeId: "node-9", outlineBlockId: "oblk-7",
    };
    const loc = locatorForBlock("sec-1", [lego], "blk-1")!;
    const backend = toBackendLocator("dlv-1", loc, lego);
    expect(backend).toEqual({
      deliverable_id: "dlv-1",
      section_id: "sec-1",
      outline_block_id: "oblk-7",
      paragraph_index: 0,
      sentence_index: null,
    });
  });

  it("prose block carries null outline_block_id (paragraph_index is the anchor)", () => {
    const loc = locatorForBlock("sec-1", [prose("a", "x")], "a")!;
    expect(toBackendLocator("dlv-1", loc, prose("a", "x")).outline_block_id).toBeNull();
  });
});

describe("newBlockId", () => {
  it("produces distinct prefixed ids", () => {
    const a = newBlockId();
    const b = newBlockId();
    expect(a).not.toBe(b);
    expect(a.startsWith("blk-")).toBe(true);
  });
});
