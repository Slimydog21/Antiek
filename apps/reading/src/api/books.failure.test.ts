import { afterEach, describe, expect, it, vi } from "vitest";

import { getBook, getBookFullText } from "./books";
import { ApiError } from "../lib/api";
import { describeFailure } from "../shared/failure";

// Failure-only transport controls. No substitute book or successful response.
const unavailable = () => new Response(
  JSON.stringify({ detail: "database read is temporarily unavailable; retry shortly" }),
  { status: 503, headers: { "Retry-After": "2" } },
);
const reads = [
  { name: "metadata", read: getBook },
  { name: "full text", read: getBookFullText },
];

afterEach(() => vi.unstubAllGlobals());

describe("book read failures", () => {
  it.each(reads)("retains service failure identity for $name", async ({ read }) => {
    const fetch = vi.fn().mockResolvedValue(unavailable());
    vi.stubGlobal("fetch", fetch);
    const failure: unknown = await read("doc-book-976d1aa3ee14f44f").catch(error => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(describeFailure(failure, { what: "open this book" })).toMatchObject({
      kind: "unavailable",
      retryable: true,
      diagnostics: { status: 503 },
    });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it.each(reads)("retains the HTTP failure when the $name error body cannot be read", async ({ read }) => {
    const response = unavailable();
    vi.spyOn(response, "text").mockRejectedValue(new TypeError("body interrupted"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const failure: unknown = await read("doc-book-976d1aa3ee14f44f").catch(error => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(describeFailure(failure).kind).toBe("unavailable");
  });

  it("keeps the owner-first, forbidden-only fallback when the public read also fails", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response("forbidden", { status: 403 }))
      .mockResolvedValueOnce(unavailable());
    vi.stubGlobal("fetch", fetch);

    const failure: unknown = await getBookFullText("doc-book-976d1aa3ee14f44f").catch(error => error);

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(fetch.mock.calls[0][0])).toContain("/books/doc-book-976d1aa3ee14f44f/owner-full-text");
    expect(String(fetch.mock.calls[1][0])).toContain("/books/doc-book-976d1aa3ee14f44f/full-text");
    expect(describeFailure(failure).kind).toBe("unavailable");
  });

  it.each([401, 410, 429, 500, 503])("does not try a public read after owner HTTP %i", async (status) => {
    const fetch = vi.fn().mockResolvedValue(new Response("failed", { status }));
    vi.stubGlobal("fetch", fetch);

    await expect(getBookFullText("doc-book-976d1aa3ee14f44f")).rejects.toMatchObject({ status });
    expect(fetch).toHaveBeenCalledOnce();
  });

  it.each(reads)("preserves the missing-book contract for $name", async ({ read }) => {
    const fetch = vi.fn().mockResolvedValue(new Response("not found", { status: 404 }));
    vi.stubGlobal("fetch", fetch);

    await expect(read("doc-book-976d1aa3ee14f44f")).rejects.toThrow("book_not_found");
    expect(fetch).toHaveBeenCalledOnce();
  });

  it.each(reads)("keeps an actual transport failure distinct for $name", async ({ read }) => {
    const networkFailure = new TypeError("Failed to fetch");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkFailure));

    const failure: unknown = await read("doc-book-976d1aa3ee14f44f").catch(error => error);

    expect(failure).toBe(networkFailure);
    expect(describeFailure(failure).kind).toBe("offline");
  });
});
