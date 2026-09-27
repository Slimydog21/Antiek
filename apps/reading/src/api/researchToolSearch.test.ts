import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));
import { apiFetch } from "../lib/api";
import { ingestResearchToolCandidate, ResearchToolIngestUnknownError, searchResearchTool } from "./researchToolSearch";

const mockedFetch = vi.mocked(apiFetch);

describe("research tool search API", () => {
  beforeEach(() => mockedFetch.mockReset());

  it("sends only the bounded search authority", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      operation_id: "tool-search-123456789",
      vendor: "x",
      status: "completed",
      candidates: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await searchResearchTool({ operationId: "tool-search-123456789", vendor: "x", query: "battery", maxResults: 10 });
    expect(mockedFetch).toHaveBeenCalledWith("/research/tools/search", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ operation_id: "tool-search-123456789", vendor: "x", query: "battery", max_results: 10 }),
    }));
  });

  it("rejects extra and unsafe response fields without echoing them", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      operation_id: "tool-search-123456789", vendor: "x", status: "completed", candidates: [], api_key: "SECRET",
    }), { status: 200 }));
    await expect(searchResearchTool({ operationId: "tool-search-123456789", vendor: "x", query: "q" }))
      .rejects.toThrow("Tool search returned an invalid response");
  });

  it("rejects malformed provenance timestamps", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({
      operation_id: "tool-search-123456789", vendor: "x", status: "completed", candidates: [{
        external_id: "1", title_or_text: "source", url: "https://x.com/a/status/1", published_at: "None", author: "a", ingestable: true,
      }],
    }), { status: 200 }));
    await expect(searchResearchTool({ operationId: "tool-search-123456789", vendor: "x", query: "q" }))
      .rejects.toThrow("Tool search returned an invalid response");
  });
});

const ingestInput = { operationId: "tool-ingest-123456789", vendor: "x" as const, externalId: "1" };
const ingestResponse = {
  operation_id: ingestInput.operationId,
  vendor: ingestInput.vendor,
  external_id: ingestInput.externalId,
  status: "completed",
  ingest_status: "ingested",
  document_id: "document-1",
  chunks_written: 2,
  skipped_reason: null,
  title: "A source",
  content_class: "article",
  source_tier: 2,
};

describe("research tool ingest API", () => {
  beforeEach(() => mockedFetch.mockReset());

  it("posts the exact ingest body", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify(ingestResponse), { status: 200 }));
    await expect(ingestResearchToolCandidate(ingestInput)).resolves.toEqual(ingestResponse);
    expect(mockedFetch).toHaveBeenCalledWith("/research/tools/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: ingestInput.operationId, vendor: "x", external_id: "1" }),
    });
  });

  it("rejects an ingest response with an extra key", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ ...ingestResponse, api_key: "SECRET" }), { status: 200 }));
    await expect(ingestResearchToolCandidate(ingestInput)).rejects.toThrow("Tool ingest returned an invalid response");
  });

  it("rejects an ingest response for another external ID", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ ...ingestResponse, external_id: "2" }), { status: 200 }));
    await expect(ingestResearchToolCandidate(ingestInput)).rejects.toThrow("Tool ingest returned an invalid response");
  });

  it("maps an unresolved outcome to ResearchToolIngestUnknownError", async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ detail: "SECRET" }), { status: 409 }));
    await expect(ingestResearchToolCandidate(ingestInput)).rejects.toBeInstanceOf(ResearchToolIngestUnknownError);
  });

  it.each([
    [429, "This provider's allowance is exhausted. Try again later."],
    [404, "The provider no longer has this item."],
  ])("maps HTTP %i to a safe message", async (status, message) => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ detail: "SECRET" }), { status }));
    await expect(ingestResearchToolCandidate(ingestInput)).rejects.toThrow(message);
  });
});
