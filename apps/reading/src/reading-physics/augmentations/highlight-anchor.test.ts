/**
 * highlight-anchor augmentation proofs (anchor-first SPR-02).
 *
 * The augmentation is the declaration layer: one anchored decoration per
 * persisted anchor, pinned to the PR-4 passage anchor, the closed class
 * vocabulary, and the registry's combine doing the same-range union — with
 * the import discipline of the chase launcher (types only, declare-don't-act).
 */
import { describe, expect, it } from "vitest";

import { anchorKey } from "../facets/decorations";
import { collectDecorations } from "../registry";
import type { ReadingContext } from "../types";
import {
  ANCHOR_DECORATION_CLASSES,
  makeHighlightAnchorAugmentation,
} from "./highlight-anchor";

const STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: { getChunk: () => Promise.reject(new Error("not wired in the slice")) },
};

function spec(over: Partial<Parameters<typeof makeHighlightAnchorAugmentation>[0]> = {}) {
  return {
    anchorId: "a-1",
    chunkId: "c-1",
    start: 10,
    end: 21,
    treatment: "active" as const,
    title: "Anchored highlight",
    ...over,
  };
}

describe("makeHighlightAnchorAugmentation", () => {
  it("declares ONE decoration pinned to the passage anchor (chunk-relative, never pixels)", () => {
    const out = collectDecorations([makeHighlightAnchorAugmentation(spec())], STUB_CTX);
    expect(out).toHaveLength(1);
    expect(out[0].anchor).toEqual({ kind: "passage", chunkId: "c-1", start: 10, end: 21 });
    expect(out[0].key).toBe(
      anchorKey({ kind: "passage", chunkId: "c-1" as never, start: 10, end: 21 }),
    );
    expect(out[0].classNames).toEqual(["anchor-active"]);
    expect(out[0].title).toBe("Anchored highlight");
  });

  it("the class vocabulary is closed: drifted maps to anchor-drifted with the honest moved title", () => {
    const out = collectDecorations(
      [
        makeHighlightAnchorAugmentation(
          spec({ treatment: "drifted", title: "Moved — re-anchored here after the text changed" }),
        ),
      ],
      STUB_CTX,
    );
    expect(out[0].classNames).toEqual(["anchor-drifted"]);
    expect(out[0].title).toContain("Moved");
    expect(Object.keys(ANCHOR_DECORATION_CLASSES).sort()).toEqual(["active", "drifted"]);
  });

  it("two anchors on the SAME range combine (classes union, titles joined) — order-independent", () => {
    const a = makeHighlightAnchorAugmentation(spec({ anchorId: "a-1", title: "one" }));
    const b = makeHighlightAnchorAugmentation(
      spec({ anchorId: "a-2", treatment: "drifted", title: "two" }),
    );
    const out = collectDecorations([a, b], STUB_CTX);
    expect(out).toHaveLength(1);
    expect(out[0].classNames).toEqual(["anchor-active", "anchor-drifted"]);
    expect(out[0].title).toBe("one · two");
  });

  it("two anchors on DIFFERENT passages stay distinct decorations with stable ids", () => {
    const out = collectDecorations(
      [
        makeHighlightAnchorAugmentation(spec({ anchorId: "a-1" })),
        makeHighlightAnchorAugmentation(spec({ anchorId: "a-2", start: 30, end: 35 })),
      ],
      STUB_CTX,
    );
    expect(out).toHaveLength(2);
  });
});
