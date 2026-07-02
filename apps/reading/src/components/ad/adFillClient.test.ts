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

  it("sanitizes live slot fills before rendering or telemetry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          slot_id: " slot:doc-1:p4:top ",
          document_id: " doc-1 ",
          page_index: "4",
          position: "top",
          kind: "ad",
          ad: {
            inventory_id: " inv-1 ",
            advertiser_display_name: "  Vertical SaaS Inc.  ",
            creative_url: "  https://example.com/c.png  ",
            landing_url: "  https://example.com/?ref=antiek  ",
          },
          house: { title: "ignored" },
          revenue_usd_cents: "120",
        }),
      }) as Response),
    );

    const result = await fetchFill({
      lens: "read",
      documentId: "doc-1",
      pageIndex: 4,
      positions: ["top"],
    });

    expect(result).toEqual({
      served: true,
      fills: [
        {
          slot_id: "slot:doc-1:p4:top",
          document_id: "doc-1",
          page_index: undefined,
          position: "top",
          kind: "ad",
          ad: {
            inventory_id: "inv-1",
            advertiser_display_name: "Vertical SaaS Inc.",
            creative_url: "https://example.com/c.png",
            landing_url: "https://example.com/?ref=antiek",
          },
          house: null,
          revenue_usd_cents: 0,
        },
      ],
    });
  });

  it.each([
    {
      creative_url: "javascript:alert(1)",
      landing_url: "https://example.com/",
    },
    {
      creative_url: "https://example.com/c.png",
      landing_url: "data:text/html,owned",
    },
    {
      creative_url: "/relative/c.png",
      landing_url: "https://example.com/",
    },
  ])("degrades unsafe paid creative URLs to house fill %#", async (adUrls) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          slot_id: "slot:doc-1:p4:top",
          document_id: "doc-1",
          page_index: 4,
          position: "top",
          kind: "ad",
          ad: {
            inventory_id: "inv-1",
            advertiser_display_name: "Unsafe Advertiser",
            ...adUrls,
          },
          house: {
            promoted_document_id: "safe-house-doc",
            title: "Safe house promo",
            author: "Curator",
          },
          revenue_usd_cents: 120,
        }),
      }) as Response),
    );

    const result = await fetchFill({
      lens: "read",
      documentId: "doc-1",
      pageIndex: 4,
      positions: ["top"],
    });

    expect(result).toEqual({
      served: true,
      fills: [
        {
          slot_id: "slot:doc-1:p4:top",
          document_id: "doc-1",
          page_index: 4,
          position: "top",
          kind: "house",
          ad: null,
          house: {
            promoted_document_id: "safe-house-doc",
            title: "Safe house promo",
            author: "Curator",
          },
          revenue_usd_cents: 0,
        },
      ],
    });
  });

  it("falls back to neutral house when a response is for the wrong edge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          position: "bottom",
          kind: "ad",
          ad: {
            inventory_id: "inv-1",
            advertiser_display_name: "Advertiser",
            creative_url: "https://example.com/c.png",
            landing_url: "https://example.com/",
          },
          revenue_usd_cents: 120,
        }),
      }) as Response),
    );

    await expect(
      fetchFill({ lens: "read", documentId: "doc-1", pageIndex: 4, positions: ["top"] }),
    ).resolves.toEqual({
      served: false,
      fills: [{ position: "top", kind: "house", house: null, revenue_usd_cents: 0 }],
    });
  });
});
