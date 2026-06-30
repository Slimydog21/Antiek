import { describe, expect, it } from "vitest";

import {
  sourcePageNumberFromExactSectionPath,
  sourcePageNumberFromSectionPath,
  zeroBasedReaderPageFromSourcePage,
} from "./sectionPath";

describe("sectionPath page locator parsing", () => {
  it("parses a leading source page locator from richer section paths", () => {
    expect(sourcePageNumberFromSectionPath("Page 17")).toBe(17);
    expect(sourcePageNumberFromSectionPath("Page 17 · Section 3.2")).toBe(17);
    expect(sourcePageNumberFromSectionPath("p.12")).toBe(12);
    expect(sourcePageNumberFromSectionPath("p 12")).toBe(12);
    expect(sourcePageNumberFromSectionPath("p. 3")).toBe(3);
  });

  it("does not parse timestamps, embedded prose, or invalid page numbers", () => {
    expect(sourcePageNumberFromSectionPath("Timestamp 00:17")).toBeNull();
    expect(sourcePageNumberFromSectionPath("Chapter Page 17")).toBeNull();
    expect(sourcePageNumberFromSectionPath("Page 0")).toBeNull();
    expect(sourcePageNumberFromSectionPath(null)).toBeNull();
  });

  it("keeps exact reader deep-link anchors stricter than source affordances", () => {
    expect(sourcePageNumberFromExactSectionPath("Page 2")).toBe(2);
    expect(sourcePageNumberFromExactSectionPath("p.2")).toBe(2);
    expect(sourcePageNumberFromExactSectionPath("p 2")).toBe(2);
    expect(sourcePageNumberFromExactSectionPath("Page 2 · Section 3")).toBeNull();
  });

  it("converts source pages to zero-based reader indexes", () => {
    expect(zeroBasedReaderPageFromSourcePage(17)).toBe(16);
    expect(zeroBasedReaderPageFromSourcePage(1)).toBe(0);
    expect(zeroBasedReaderPageFromSourcePage(null)).toBeNull();
    expect(zeroBasedReaderPageFromSourcePage(undefined)).toBeNull();
  });
});
