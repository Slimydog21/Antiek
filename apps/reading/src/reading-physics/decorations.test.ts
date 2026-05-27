/**
 * decorations.test.ts — SPR-02, the proving slice (the PURE half).
 *
 * The combine rule (§5.1) and the §9.0 servability augmentation, tested in
 * isolation (no DOM render — that's the byte-equivalence half, which lives in
 * MasterMdViewer.test.tsx because it needs JSX + the React render harness):
 *
 *   - the combine rule (§5.1): empty input, overlapping ranges from one
 *     augmentation, same-range class union + title join, and the load-bearing
 *     property: ORDER-INDEPENDENCE (swapping declaration order is byte-identical);
 *   - the §9.0 servability augmentation declares the right closed-vocabulary
 *     verdict for servable + non-servable sources, and reveals NOTHING on the
 *     restricted branch (never declares SERVABLE_CLASS for a withheld source).
 */
import { describe, expect, it } from "vitest";

import type { Anchor, ChunkId, Decoration } from "./types";
import type { ReadingContext } from "./types";
import { anchorKey, combineDecorations } from "./facets/decorations";
import {
  RESTRICTED_CLASS,
  RESTRICTED_TITLE,
  SERVABLE_CLASS,
  SERVABLE_TITLE,
  makeServabilityAugmentation,
} from "./augmentations/servability";
import { collectDecorations } from "./registry";

function chunkAnchor(id: string): Anchor {
  return { kind: "chunk", chunkId: id as ChunkId };
}

/** A minimal ReadingContext stub: the servability augmentation closes over
 *  its sources and never reads ctx, so this only needs to satisfy the shape. */
const STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: {
    getChunk: () => Promise.reject(new Error("not wired in the slice")),
  },
};

// ── The combine rule (§5.1) — rigor #3 edge cases ──────────────────────────

describe("combineDecorations — the §5.1 combine rule", () => {
  it("empty input is a no-op (returns [])", () => {
    expect(combineDecorations([])).toEqual([]);
  });

  it("a single decoration resolves to its own range + class + (no) title", () => {
    const d: Decoration = { anchor: chunkAnchor("c1"), className: "alpha" };
    const out = combineDecorations([d]);
    expect(out).toHaveLength(1);
    expect(out[0].key).toBe(anchorKey(chunkAnchor("c1")));
    expect(out[0].classNames).toEqual(["alpha"]);
    expect(out[0].title).toBe("");
  });

  it("two decorations on the SAME range union their classes (de-duplicated, sorted)", () => {
    const out = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "beta alpha" },
      { anchor: chunkAnchor("c1"), className: "alpha gamma" },
    ]);
    expect(out).toHaveLength(1);
    // union { alpha, beta, gamma }, sorted; alpha de-duplicated.
    expect(out[0].classNames).toEqual(["alpha", "beta", "gamma"]);
  });

  it("two decorations on DIFFERENT ranges stay separate, sorted by key", () => {
    const out = combineDecorations([
      { anchor: chunkAnchor("c2"), className: "two" },
      { anchor: chunkAnchor("c1"), className: "one" },
    ]);
    expect(out.map((d) => d.key)).toEqual([
      anchorKey(chunkAnchor("c1")),
      anchorKey(chunkAnchor("c2")),
    ]);
  });

  it("same-range titles join as the SORTED set joined by ' · ' (§5.1)", () => {
    const out = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "x", title: "Zed" },
      { anchor: chunkAnchor("c1"), className: "y", title: "Alpha" },
    ]);
    expect(out[0].title).toBe("Alpha · Zed");
  });

  it("is ORDER-INDEPENDENT — swapping declaration order is byte-identical", () => {
    const a: Decoration = { anchor: chunkAnchor("c1"), className: "beta", title: "B" };
    const b: Decoration = { anchor: chunkAnchor("c1"), className: "alpha", title: "A" };
    const forward = combineDecorations([a, b]);
    const reverse = combineDecorations([b, a]);
    // The whole resolved structure is identical regardless of order — the
    // property the entire facet model rests on (CodeMirror-style free compose).
    expect(reverse).toEqual(forward);
    expect(forward[0].classNames).toEqual(["alpha", "beta"]);
    expect(forward[0].title).toBe("A · B");
  });

  it("an overlapping range from one augmentation merges without crashing", () => {
    // Same augmentation declaring two decorations on overlapping (here:
    // identical) ranges — both apply, union of classes, no throw.
    const out = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "highlight" },
      { anchor: chunkAnchor("c1"), className: "underline" },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].classNames).toEqual(["highlight", "underline"]);
  });

  it("an empty className contributes no class (no crash, no empty token)", () => {
    const out = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "" },
      { anchor: chunkAnchor("c1"), className: "real" },
    ]);
    expect(out[0].classNames).toEqual(["real"]);
  });
});

// ── The §9.0 servability augmentation declares the right verdict (PR-6) ────

describe("ServabilityAugmentation — declares the §9.0 verdict (PR-6)", () => {
  it("declares no decorations for an empty source set", () => {
    const aug = makeServabilityAugmentation([]);
    expect(collectDecorations([aug], STUB_CTX)).toEqual([]);
  });

  it("declares the SERVABLE class + tooltip for a servable source", () => {
    const aug = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const out = collectDecorations([aug], STUB_CTX);
    expect(out).toHaveLength(1);
    expect(out[0].classNames).toEqual([SERVABLE_CLASS]);
    expect(out[0].title).toBe(SERVABLE_TITLE);
  });

  it("declares the RESTRICTED class + tooltip for a NON-servable source (§9.0)", () => {
    const aug = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: false },
    ]);
    const out = collectDecorations([aug], STUB_CTX);
    expect(out).toHaveLength(1);
    // The restricted branch carries ONLY the restricted class — it never
    // declares SERVABLE_CLASS, so the surface can never be tricked into the
    // openable branch (§9.0: the augmentation cannot reveal a withheld body).
    expect(out[0].classNames).toEqual([RESTRICTED_CLASS]);
    expect(out[0].classNames).not.toContain(SERVABLE_CLASS);
    expect(out[0].title).toBe(RESTRICTED_TITLE);
  });

  it("declares one verdict per source, keyed by the source's anchor", () => {
    const aug = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
      { representativeChunkId: "c2", servable: false },
    ]);
    const out = collectDecorations([aug], STUB_CTX);
    const byKey = new Map(out.map((d) => [d.key, d]));
    expect(byKey.get(anchorKey(chunkAnchor("c1")))!.classNames).toEqual([SERVABLE_CLASS]);
    expect(byKey.get(anchorKey(chunkAnchor("c2")))!.classNames).toEqual([RESTRICTED_CLASS]);
  });
});
