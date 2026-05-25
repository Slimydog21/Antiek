import { describe, expect, it } from "vitest";

import { computeHighlights, findAnchor, toSegments } from "./anchor";

const RAW = "# Report\n\nGPUs gate model scale. Capital is abundant in this market.\n\nThe team is small.";

describe("findAnchor — whitespace-normalized content anchoring", () => {
  it("locates a verbatim anchor at its original offsets", () => {
    const span = findAnchor(RAW, "Capital is abundant in this market.");
    expect(span).not.toBeNull();
    expect(RAW.slice(span!.start, span!.end)).toBe("Capital is abundant in this market.");
  });

  it("locates an anchor whose whitespace differs from the document", () => {
    // Anchor reflowed (newline + double spaces) — normalized match still finds it.
    const span = findAnchor(RAW, "GPUs gate model scale.\n   Capital is abundant in this market.");
    expect(span).not.toBeNull();
    expect(RAW.slice(span!.start, span!.end)).toContain("GPUs gate model scale.");
    expect(RAW.slice(span!.start, span!.end)).toContain("Capital is abundant in this market.");
  });

  it("returns null (stale) when the anchor text was edited away", () => {
    const edited = "# Report\n\nThe team is small.";
    expect(findAnchor(edited, "GPUs gate model scale.")).toBeNull();
  });
});

describe("anchor survives an edit elsewhere (the mandatory gate)", () => {
  it("re-anchors at the shifted offset after an unrelated edit before it", () => {
    const anchor = "Capital is abundant in this market.";
    const before = findAnchor(RAW, anchor)!;
    // Insert text BEFORE the anchored span; offsets shift, content match holds.
    const editedRaw = RAW.replace("# Report", "# Report (revised draft, expanded heading)");
    const after = findAnchor(editedRaw, anchor)!;
    expect(after).not.toBeNull();
    expect(editedRaw.slice(after.start, after.end)).toBe(anchor);
    expect(after.start).toBeGreaterThan(before.start); // shifted, not broken
  });

  it("keeps anchoring when whitespace inside the region is reflowed", () => {
    const reflowed = RAW.replace("GPUs gate model scale. Capital", "GPUs gate model scale.\n\nCapital");
    const span = findAnchor(reflowed, "GPUs gate model scale. Capital is abundant in this market.");
    expect(span).not.toBeNull();
  });
});

describe("computeHighlights + toSegments", () => {
  const notes = [
    { node_id: "i1", kind: "insight" as const, anchors: ["GPUs gate model scale. Capital is abundant in this market."] },
    { node_id: "q1", kind: "question" as const, anchors: ["The team is small."] },
    { node_id: "stale1", kind: "insight" as const, anchors: ["a sentence that is not in the document"] },
  ];

  it("places non-overlapping highlights and reports stale anchors", () => {
    const { highlights, staleNoteIds } = computeHighlights(RAW, notes);
    expect(staleNoteIds).toEqual(["stale1"]);
    expect(highlights.map((h) => h.noteId)).toEqual(["i1", "q1"]); // sorted by start
    // No crossing ranges.
    for (let i = 1; i < highlights.length; i++) {
      expect(highlights[i].start).toBeGreaterThanOrEqual(highlights[i - 1].end);
    }
  });

  it("toSegments reconstructs the original text exactly", () => {
    const { highlights } = computeHighlights(RAW, notes);
    const segments = toSegments(RAW, highlights);
    expect(segments.map((s) => s.text).join("")).toBe(RAW);
    // The highlighted segments carry their note.
    const highlighted = segments.filter((s) => s.highlight);
    expect(highlighted.length).toBe(2);
  });
});
