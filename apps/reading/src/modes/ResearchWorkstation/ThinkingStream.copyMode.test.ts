/**
 * ThinkingStream.copyMode.test.ts — the pure copy-mode helpers (herdr
 * transfer P1): search over narrated lines + <mark> splitting.
 */
import { describe, expect, it } from "vitest";

import { findMatchIndices, splitMatches } from "./ThinkingStream";

describe("findMatchIndices", () => {
  const lines = [
    "Breaking your question into parts",
    "Looking for evidence on retrieval",
    "Found supporting points",
    "Writing the answer",
  ];

  it("finds case-insensitive substring matches", () => {
    // "in" is a substring of "into" (0), "Looking" (1), "supporting" (2),
    // "Writing" (3) — every line matches.
    expect(findMatchIndices(lines, "in")).toEqual([0, 1, 2, 3]);
    // "the" appears only in the answer line.
    expect(findMatchIndices(lines, "the")).toEqual([3]);
    // Case-insensitivity: "BREAKING" matches line 0.
    expect(findMatchIndices(lines, "breaking")).toEqual([0]);
  });

  it("empty or whitespace query matches nothing", () => {
    expect(findMatchIndices(lines, "")).toEqual([]);
    expect(findMatchIndices(lines, "   ")).toEqual([]);
  });

  it("no match yields an empty list", () => {
    expect(findMatchIndices(lines, "zzz")).toEqual([]);
  });
});

describe("splitMatches", () => {
  it("empty query returns the whole text as one non-match segment", () => {
    expect(splitMatches("hello world", "")).toEqual([{ text: "hello world", match: false }]);
  });

  it("splits around every occurrence, case-insensitively", () => {
    expect(splitMatches("Foo bar FOO", "foo")).toEqual([
      { text: "Foo", match: true },
      { text: " bar ", match: false },
      { text: "FOO", match: true },
    ]);
  });

  it("no match returns the whole text unmarked", () => {
    expect(splitMatches("hello", "zzz")).toEqual([{ text: "hello", match: false }]);
  });

  it("overlapping query at the edges is handled", () => {
    expect(splitMatches("aaaa", "aa")).toEqual([
      { text: "aa", match: true },
      { text: "aa", match: true },
    ]);
  });
});
