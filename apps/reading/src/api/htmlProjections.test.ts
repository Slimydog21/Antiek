import { afterEach, describe, expect, it, vi } from "vitest";
import { getHtmlProjectionByDocument, HtmlProjectionError } from "./htmlProjections";

const valid = { identity: { source_asset_id: "asset-1", source_document_id: "doc/a b", source_sha256: "b".repeat(64), converter_id: "converter", converter_version: "1", sanitizer_policy: "strict", sanitizer_version: "1" }, projection_id: `hproj-${"c".repeat(64)}`, html_sha256: "a".repeat(64), html: '<article id="antiek-anchor-a">Hello</article>', anchor_mappings: [{ source_locator: { kind: "semantic", semantic_id: "one" }, state: "resolved", html_anchor_id: "antiek-anchor-a", candidates: [] }] };

afterEach(() => vi.restoreAllMocks());

describe("getHtmlProjectionByDocument", () => {
  it("encodes the document id and validates a successful response", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(valid)));
    await expect(getHtmlProjectionByDocument("doc/a b")).resolves.toMatchObject({ projection_id: `hproj-${"c".repeat(64)}` });
    expect(String(fetch.mock.calls[0][0]).endsWith("/html-projections/by-document/doc%2Fa%20b")).toBe(true);
  });

  it("preserves status and bounded JSON detail on HTTP errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Multiple ready HTML projections" }), { status: 409 }));
    await expect(getHtmlProjectionByDocument("doc")).rejects.toEqual(expect.objectContaining<Partial<HtmlProjectionError>>({ status: 409, detail: "Multiple ready HTML projections" }));
  });

  it.each([
    { ...valid, identity: null }, { ...valid, html_sha256: "bad" }, { ...valid, html: 3 },
    { ...valid, identity: { ...valid.identity, source_document_id: "wrong-document" } },
    { ...valid, anchor_mappings: [{ source_locator: { nested: {} }, state: "resolved", html_anchor_id: "a", candidates: [] }] },
  ])("rejects malformed unknown JSON", async (body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body)));
    await expect(getHtmlProjectionByDocument("doc/a b")).rejects.toThrow(/Invalid HTML projection/);
  });
});
