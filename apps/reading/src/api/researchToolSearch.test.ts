import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));
import { apiFetch } from "../lib/api";
import { searchResearchTool } from "./researchToolSearch";

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
        external_id: "1", title_or_text: "source", url: "https://x.com/a/status/1", published_at: "None", author: "a",
      }],
    }), { status: 200 }));
    await expect(searchResearchTool({ operationId: "tool-search-123456789", vendor: "x", query: "q" }))
      .rejects.toThrow("Tool search returned an invalid response");
  });
});
