import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchFill } from "./adFillClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchFill", () => {
  it("calls the live per-slot fill route for each requested reader edge", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const parsed = new URL(url, "http://test.local");
      const position = parsed.searchParams.get("position") ?? "top";
      return {
        ok: true,
        json: async () => ({
          slot_id: `slot:doc-1:p4:${position}`,
          document_id: parsed.searchParams.get("document_id"),
          page_index: Number(parsed.searchParams.get("page_index")),
          position,
          kind: "house",
          house: { promoted_document_id: "doc-2", title: "Promotable", author: "A" },
          revenue_usd_cents: 0,
        }),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchFill({
      lens: "read",
      documentId: "doc-1",
      pageIndex: 4,
      positions: ["top", "bottom"],
    });

    expect(result.served).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const urls = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://test.local"));
    expect(urls.map((u) => u.pathname)).toEqual(["/api/ad/fill", "/api/ad/fill"]);
    expect(urls.map((u) => u.searchParams.get("document_id"))).toEqual(["doc-1", "doc-1"]);
    expect(urls.map((u) => u.searchParams.get("page_index"))).toEqual(["4", "4"]);
    expect(urls.map((u) => u.searchParams.get("position"))).toEqual(["top", "bottom"]);
    expect(result.fills.map((f) => f.position)).toEqual(["top", "bottom"]);
    expect(result.fills[0].slot_id).toBe("slot:doc-1:p4:top");
  });

  it("does not call the route when no active reader document is known", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchFill({
      lens: "research",
      documentId: null,
      pageIndex: null,
      positions: ["top", "bottom"],
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.served).toBe(false);
    expect(result.fills).toEqual([
      { position: "top", kind: "house", house: null, revenue_usd_cents: 0 },
      { position: "bottom", kind: "house", house: null, revenue_usd_cents: 0 },
    ]);
  });

  it.each([1.5, -1, Number.MAX_SAFE_INTEGER + 1, Number.POSITIVE_INFINITY])(
    "does not call the route for malformed page index %s",
    async (pageIndex) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);

      const result = await fetchFill({
        lens: "read",
        documentId: "doc-1",
        pageIndex,
        positions: ["top"],
      });

      expect(fetchMock).not.toHaveBeenCalled();
      expect(result).toEqual({
        fills: [{ position: "top", kind: "house", house: null, revenue_usd_cents: 0 }],
        served: false,
      });
    },
  );

  it("falls back to neutral house fills when the live route fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 }) as Response));

    const result = await fetchFill({
      lens: "read",
      documentId: "doc-1",
      pageIndex: 1,
      positions: ["top"],
    });

    expect(result.served).toBe(false);
    expect(result.fills).toEqual([
      { position: "top", kind: "house", house: null, revenue_usd_cents: 0 },
    ]);
  });
});
