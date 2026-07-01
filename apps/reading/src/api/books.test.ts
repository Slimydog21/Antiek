import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * books api — meta-reading client boundary (Read SPR-08 M4).
 *
 * The surface tests pin the component-level call shape. This file pins the API
 * client wire contract: default hard owned-corpus scope, explicit rollback
 * overrides, and backend error messages.
 */

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: apiFetchMock,
}));

import { generateMetaReading } from "./books";

function metaReadingResponse() {
  return {
    asset_id: "mr-api-1",
    report: "owned-corpus synthesis",
    citations: [],
    length_unit: "pages",
    length_amount: 3,
    word_budget: 900,
    truncated: false,
    corpus_scope: "hard",
    corpus_document_ids: ["doc-1"],
    empty: false,
    context_chunk_count: 1,
  };
}

function postedMetaReadingBody(): Record<string, unknown> {
  const [, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue(
    new Response(JSON.stringify(metaReadingResponse()), { status: 200 }),
  );
});

describe("books api — meta-reading boundary", () => {
  it("defaults meta-reading generation to the proposed hard owned-corpus scope", async () => {
    const result = await generateMetaReading({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/corpus/meta-reading");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedMetaReadingBody()).toEqual({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
      research_tier: "deep",
      corpus_scope: "hard",
    });
    expect(result).toEqual(metaReadingResponse());
  });

  it("preserves explicit rollback scope, tier, and document picks", async () => {
    await generateMetaReading({
      prompt: "owned corpus with explicit picks",
      length_unit: "minutes",
      length_amount: 12,
      research_tier: "fast",
      corpus_scope: "soft",
      document_ids: ["doc-a", "doc-b"],
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(postedMetaReadingBody()).toEqual({
      prompt: "owned corpus with explicit picks",
      length_unit: "minutes",
      length_amount: 12,
      research_tier: "fast",
      corpus_scope: "soft",
      document_ids: ["doc-a", "doc-b"],
    });
  });

  it("surfaces the backend's stated length-bound error", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Length is capped at 60 pages; got 999." }),
        { status: 422 },
      ),
    );

    await expect(
      generateMetaReading({
        prompt: "too long",
        length_unit: "pages",
        length_amount: 999,
      }),
    ).rejects.toThrow("Length is capped at 60 pages; got 999.");
  });

  it("falls back when a length-bound error omits a string detail", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: [{ msg: "bad length" }] }), {
        status: 422,
      }),
    );

    await expect(
      generateMetaReading({
        prompt: "too long",
        length_unit: "pages",
        length_amount: 999,
      }),
    ).rejects.toThrow("Invalid length.");
  });

  it("surfaces provider unavailability as the reader-facing meta-reading message", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no model", { status: 503 }));

    await expect(
      generateMetaReading({
        prompt: "summarize",
        length_unit: "minutes",
        length_amount: 10,
      }),
    ).rejects.toThrow(/Meta-reading isn.t available right now\./);
  });

  it("keeps unexpected backend failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(
      generateMetaReading({
        prompt: "summarize",
        length_unit: "pages",
        length_amount: 3,
      }),
    ).rejects.toThrow("POST /corpus/meta-reading: HTTP 500");
  });
});
