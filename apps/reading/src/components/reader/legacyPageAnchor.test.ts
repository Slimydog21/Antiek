import { describe, expect, it } from "vitest";
import type { HtmlProjectionAnchorMapping } from "../../api/htmlProjections";
import { parseLegacyPageLocator, resolveLegacyPageAnchor } from "./legacyPageAnchor";

const anchor = (char: string) => `antiek-anchor-${char.repeat(64)}`;

const mapping = (kind: string, page: number, anchorId: string): HtmlProjectionAnchorMapping => ({
  source_locator: { kind, page }, state: "resolved", html_anchor_id: anchorId, candidates: [],
});

describe("resolveLegacyPageAnchor", () => {
  it("resolves exactly one matching PDF page anchor", () => {
    expect(resolveLegacyPageAnchor([mapping("pdf_page_bbox", 3, anchor("a"))], 3))
      .toEqual({ kind: "resolved", anchorId: anchor("a") });
  });

  it("reports no matching anchor", () => {
    expect(resolveLegacyPageAnchor([mapping("semantic", 3, "other")], 3))
      .toEqual({ kind: "not-found" });
  });

  it("reports duplicate matching anchors as ambiguous", () => {
    expect(resolveLegacyPageAnchor([
      mapping("pdf_page_bbox", 3, "a"), mapping("pdf_page_bbox", 3, "b"),
    ], 3)).toEqual({ kind: "ambiguous", anchorIds: ["a", "b"] });
  });

  it.each([0, -1, 1.5, Number.NaN])("rejects invalid page %s", (page) => {
    expect(resolveLegacyPageAnchor([], page)).toEqual({ kind: "invalid" });
  });

  it("rejects a non-canonical anchor returned by a matching mapping", () => {
    expect(resolveLegacyPageAnchor([mapping("pdf_page_bbox", 3, "anchor-3")], 3))
      .toEqual({ kind: "invalid-anchor" });
  });
});

describe("parseLegacyPageLocator", () => {
  it.each([["Page 1", 1], ["Page 17 · Section 3.2", 17]])("parses strict %s", (value, expected) => {
    expect(parseLegacyPageLocator(value)).toBe(expected);
  });

  it.each([null, "", "p.12", "Page 0", "Page -1", "Page 12 trailing", "prefix Page 12"])("rejects %s", (value) => {
    expect(parseLegacyPageLocator(value)).toBeNull();
  });
});
