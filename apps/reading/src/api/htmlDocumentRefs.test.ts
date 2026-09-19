import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchHtmlDocumentReference,
  isHtmlDocumentIdentifier,
  parseHtmlDocumentResumeRef,
  parseHydratedHtmlDocument,
} from "./htmlDocumentRefs";

const reference = { resolver: "hosted_document" as const, document_id: "same-id" };
const hydrated = {
  schema_version: 1,
  ...reference,
  title: "Current title",
  view_format: "html",
  html: "<!doctype html><html><body>current bytes</body></html>",
};

describe("HTML document reference transport is closed", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("accepts only exact resolver-qualified references and bounded identifiers", () => {
    expect(parseHtmlDocumentResumeRef(reference)).toEqual(reference);
    expect(parseHtmlDocumentResumeRef({ ...reference, resolver: "engagement_document" })).toEqual({
      resolver: "engagement_document",
      document_id: "same-id",
    });
    expect(parseHtmlDocumentResumeRef({ ...reference, html: "raw" })).toBeNull();
    expect(parseHtmlDocumentResumeRef({ document_id: "same-id" })).toBeNull();
    expect(parseHtmlDocumentResumeRef({ ...reference, document_id: " same-id" })).toBeNull();
    expect(parseHtmlDocumentResumeRef({ ...reference, document_id: "same\u0000id" })).toBeNull();
    expect(isHtmlDocumentIdentifier("é".repeat(256))).toBe(true);
    expect(isHtmlDocumentIdentifier(`${"é".repeat(256)}x`)).toBe(false);
  });

  it.each([
    { ...hydrated, extra: "open schema" },
    { ...hydrated, resolver: "engagement_document" },
    { ...hydrated, document_id: "other" },
    { ...hydrated, schema_version: 2 },
    { ...hydrated, view_format: "pdf" },
    { ...hydrated, html: "%PDF-1.7 private bytes" },
    { ...hydrated, html: "plain backend text" },
    { ...hydrated, html: "" },
  ])("rejects malformed or non-HTML backend response %#", (body) => {
    expect(() => parseHydratedHtmlDocument(body, reference)).toThrow(
      "invalid HTML document reference response",
    );
  });

  it("uses an authenticated no-store GET and validates the exact identity", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(hydrated), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchHtmlDocumentReference(reference)).resolves.toEqual(hydrated);
    expect(fetch.mock.calls[0][0]).toContain(
      "/account/html-document-refs/hosted_document/same-id",
    );
    expect(fetch.mock.calls[0][1]).toMatchObject({
      credentials: "include",
      cache: "no-store",
    });
  });
});
