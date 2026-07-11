import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  parseTwinSearchResponse,
  searchTwins,
  TwinSearchHttpError,
} from "./twinSearch";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const hit = {
  twin_id: "t1",
  parent_asset_id: "p1",
  score: 2.5,
  matched_insights: ["scaling laws"],
  matched_questions: [],
  source_label: null,
};

describe("parseTwinSearchResponse", () => {
  it("accepts valid body and rejects count/hits mismatch", () => {
    const ok = parseTwinSearchResponse({
      query: "scaling",
      count: 1,
      hits: [hit],
    });
    expect(ok.hits[0].twin_id).toBe("t1");
    expect(() =>
      parseTwinSearchResponse({
        query: "scaling",
        count: 2,
        hits: [hit],
      }),
    ).toThrow(/count/);
    expect(() =>
      parseTwinSearchResponse({
        query: "x",
        count: 1,
        hits: [{ ...hit, score: "high" }],
      }),
    ).toThrow(/score/);
    for (const score of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
      expect(() =>
        parseTwinSearchResponse({
          query: "x",
          count: 1,
          hits: [{ ...hit, score }],
        }),
      ).toThrow(/score/);
    }
    expect(() =>
      parseTwinSearchResponse({
        query: "x",
        count: 1,
        hits: [{ ...hit, matched_insights: [null as unknown as string] }],
      }),
    ).toThrow(/matched_insights/);
    const { source_label: _sl, ...noLabel } = hit;
    void _sl;
    expect(() =>
      parseTwinSearchResponse({
        query: "x",
        count: 1,
        hits: [noLabel],
      }),
    ).toThrow(/source_label/);
    expect(() =>
      parseTwinSearchResponse({
        query: "x",
        count: 1,
        hits: [{ ...hit, source_label: 1 as unknown as string }],
      }),
    ).toThrow(/source_label/);
  });
});

describe("searchTwins", () => {
  it("GETs /twins/search and parses hits", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        query: "scaling",
        count: 1,
        hits: [hit],
      }),
      text: async () => "",
    } as unknown as Response);
    const body = await searchTwins({ q: "scaling", limit: 10 });
    expect(body.count).toBe(1);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringMatching(/^\/twins\/search\?/),
      expect.objectContaining({ method: "GET" }),
    );
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toMatch(/q=scaling/);
    expect(url).toMatch(/limit=10/);
  });

  it("rejects empty q and bad limit before network", async () => {
    await expect(searchTwins({ q: "  " })).rejects.toThrow(/q must be non-empty/);
    await expect(searchTwins({ q: "ok", limit: 0 })).rejects.toThrow(/limit/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "boom",
      json: async () => ({}),
    } as unknown as Response);
    await expect(searchTwins({ q: "x" })).rejects.toBeInstanceOf(
      TwinSearchHttpError,
    );
  });
});
