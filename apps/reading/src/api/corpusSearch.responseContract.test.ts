import { afterEach, describe, expect, it, vi } from "vitest";

import { corpusSearch } from "./corpusSearch";

afterEach(() => vi.unstubAllGlobals());

it("rejects a malformed successful response instead of admitting it as search results", async () => {
  const transport = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", transport);

  await expect(corpusSearch("reading context")).rejects.toThrow("Search returned an invalid response.");
  expect(transport).toHaveBeenCalledOnce();
  expect(transport).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ credentials: "include" }));
});

function serve(body: string, status = 200) {
  const transport = vi.fn<typeof fetch>().mockResolvedValue(new Response(body, { status }));
  vi.stubGlobal("fetch", transport);
  return transport;
}

describe("Successful-response contract (synthetic malformed bodies only)", () => {
  it.each([
    { label: "null response", body: null },
    { label: "array response", body: [] },
    { label: "missing query", body: { hits: [], count: 0 } },
    { label: "non-string query", body: { query: null, hits: [], count: 0 } },
    { label: "missing hits", body: { query: "query", count: 0 } },
    { label: "null hits", body: { query: "query", hits: null, count: 0 } },
    { label: "object hits", body: { query: "query", hits: {}, count: 0 } },
    { label: "missing count", body: { query: "query", hits: [] } },
    { label: "string count", body: { query: "query", hits: [], count: "0" } },
    { label: "fractional count", body: { query: "query", hits: [], count: 0.5 } },
    { label: "null hit", body: { query: "query", hits: [null], count: 1 } },
    { label: "array hit", body: { query: "query", hits: [[]], count: 1 } },
  ])("rejects $label", async ({ body }) => {
    serve(JSON.stringify(body));
    await expect(corpusSearch("query")).rejects.toEqual(new Error("Search returned an invalid response."));
  });

  const hitFields: Record<string, unknown> = {
    chunk_id: "synthetic-chunk",
    document_id: "synthetic-document",
    document_title: null,
    page_index: null,
    page_resolved: false,
    snippet: "synthetic text",
    similarity: 0,
  };

  it.each(Object.keys(hitFields))("rejects a hit missing %s", async (field) => {
    const incomplete = { ...hitFields };
    delete incomplete[field];
    serve(JSON.stringify({ query: "query", hits: [incomplete], count: 1 }));
    await expect(corpusSearch("query")).rejects.toEqual(new Error("Search returned an invalid response."));
  });

  it.each([
    { field: "chunk_id", value: null },
    { field: "chunk_id", value: 1 },
    { field: "document_id", value: null },
    { field: "document_id", value: {} },
    { field: "document_title", value: false },
    { field: "document_title", value: {} },
    { field: "page_index", value: "1" },
    { field: "page_index", value: 0.5 },
    { field: "page_resolved", value: null },
    { field: "page_resolved", value: "false" },
    { field: "snippet", value: null },
    { field: "snippet", value: {} },
    { field: "similarity", value: null },
    { field: "similarity", value: "0.5" },
  ])("rejects an invalid $field scalar: $value", async ({ field, value }) => {
    serve(JSON.stringify({ query: "query", hits: [{ ...hitFields, [field]: value }], count: 1 }));
    await expect(corpusSearch("query")).rejects.toEqual(new Error("Search returned an invalid response."));
  });

  it.each([
    '{"query":"query","hits":[],"count":1e400}',
    '{"query":"query","hits":[{"chunk_id":"synthetic","document_id":"synthetic","document_title":null,"page_index":null,"page_resolved":false,"snippet":"synthetic","similarity":1e400}],"count":1}',
  ])("rejects non-finite JSON numbers", async (body) => {
    serve(body);
    await expect(corpusSearch("query")).rejects.toEqual(new Error("Search returned an invalid response."));
  });

  it.each(["", '<html>synthetic-private-body</html>', '{"synthetic-private-body":'])
    ("does not expose undecodable response text", async (body) => {
      serve(body);
      await expect(corpusSearch("query")).rejects.toEqual(new Error("Search returned an invalid response."));
    });
});

describe("Existing request and failure contracts", () => {
  it("keeps blank queries local without making a request", async () => {
    const transport = serve("synthetic request must not run");
    await expect(corpusSearch(" \n\t ")).resolves.toEqual({ query: " \n\t ", hits: [], count: 0 });
    expect(transport).not.toHaveBeenCalled();
  });

  it("keeps query/options encoding and authenticated transport on malformed responses", async () => {
    const transport = serve("{}");
    const query = "A & B/é?\nsecond line";
    const documentId = "synthetic id/?&=é";
    await expect(corpusSearch(query, { documentId, limit: 7 })).rejects.toThrow("invalid response");
    const [input, init] = transport.mock.calls[0];
    const params = new URL(String(input), "https://synthetic.invalid").searchParams;
    expect(params.get("q")).toBe(query);
    expect(params.get("document_id")).toBe(documentId);
    expect(params.get("limit")).toBe("7");
    expect(init?.credentials).toBe("include");
  });

  it.each([
    { status: 503, message: "Search is temporarily unavailable." },
    { status: 401, message: "GET /corpus/search: HTTP 401" },
    { status: 403, message: "GET /corpus/search: HTTP 403" },
    { status: 500, message: "GET /corpus/search: HTTP 500" },
  ])("preserves the HTTP $status failure before decoding", async ({ status, message }) => {
    serve("synthetic-private-body", status);
    await expect(corpusSearch("query")).rejects.toEqual(new Error(message));
  });

  it("preserves a rejected transport failure", async () => {
    const transport = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("synthetic network failure"));
    vi.stubGlobal("fetch", transport);
    await expect(corpusSearch("query")).rejects.toEqual(new TypeError("synthetic network failure"));
  });
});
