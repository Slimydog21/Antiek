import { describe, expect, it } from "vitest";

import { canonicalAnchor, legacyWrestleRedirectTarget } from "./routes/documentRoutes";

describe("legacy Wrestle route compatibility", () => {
  const anchor = `antiek-anchor-${"a".repeat(64)}`;

  it("redirects the index to the canonical document index", () => {
    expect(legacyWrestleRedirectTarget()).toBe("/documents");
  });

  it("preserves only a valid canonical anchor", () => {
    expect(legacyWrestleRedirectTarget("doc 1/α", `?anchor=${anchor}`)).toBe(
      `/documents/doc%201%2F%CE%B1?anchor=${anchor}`,
    );
  });

  it("drops invalid anchors, page, extraneous query, and hash state", () => {
    expect(
      legacyWrestleRedirectTarget(
        "doc-1",
        "?anchor=antiek-anchor-ABC&page=9&debug=true#old",
      ),
    ).toBe("/documents/doc-1");
  });

  it("accepts canonical anchors only", () => {
    expect(canonicalAnchor(`?anchor=${anchor}&page=9`)).toBe(anchor);
    expect(canonicalAnchor("?anchor=antiek-anchor-z")).toBeUndefined();
    expect(canonicalAnchor(`?anchor=antiek-anchor-${"A".repeat(64)}`)).toBeUndefined();
  });

  it("is never a loop and produces the canonical route", () => {
    const target = legacyWrestleRedirectTarget("doc-1", "?page=2");
    expect(target).toBe("/documents/doc-1");
    expect(target.startsWith("/wrestle")).toBe(false);
  });
});
