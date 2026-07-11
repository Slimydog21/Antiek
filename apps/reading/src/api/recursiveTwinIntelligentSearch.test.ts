import { describe, expect, it } from "vitest";
import {
  formatTwinSearchSummary,
  searchTwinSubstrate,
} from "./recursiveTwinIntelligentSearch";

const corpus = [
  {
    twin_id: "t1",
    parent_asset_id: "a1",
    insights: ["scaling laws hold under compute constraints"],
    questions: ["what is the counterexample?"],
    source_label: "arxiv-paper",
  },
  {
    twin_id: "t2",
    parent_asset_id: "a2",
    insights: ["market structure differs from scaling"],
    questions: ["how does regulation change the story?"],
  },
  {
    twin_id: "t3",
    parent_asset_id: "a3",
    insights: ["unrelated note about cooking"],
    questions: ["what spice pairs with thyme?"],
  },
];

describe("searchTwinSubstrate", () => {
  it("finds term overlaps without inventing hits", () => {
    const r = searchTwinSubstrate({
      query: "scaling compute",
      records: corpus,
    });
    expect(r.remote_index_queried).toBe(false);
    expect(r.hits.length).toBeGreaterThanOrEqual(1);
    expect(r.hits[0].twin_id).toBe("t1");
    expect(r.hits[0].matched_fields).toContain("insights");
    expect(r.authority).toBe("twin_intelligent_search_advisory");
  });

  it("empty corpus yields zero hits", () => {
    const r = searchTwinSubstrate({
      query: "scaling",
      records: [],
    });
    expect(r.hits).toEqual([]);
    expect(r.remote_index_queried).toBe(false);
  });

  it("rejects empty query", () => {
    expect(() =>
      searchTwinSubstrate({ query: "  ", records: corpus }),
    ).toThrow(/query/);
  });

  it("rejects query without usable tokens", () => {
    expect(() =>
      searchTwinSubstrate({ query: "a b", records: corpus }),
    ).toThrow(/token/);
  });

  it("respects limit", () => {
    const r = searchTwinSubstrate({
      query: "scaling market regulation",
      records: corpus,
      limit: 1,
    });
    expect(r.hits.length).toBeLessThanOrEqual(1);
  });

  it("does not invent match for unrelated query", () => {
    const r = searchTwinSubstrate({
      query: "quantum entanglement teleportation",
      records: corpus,
    });
    expect(r.hits).toEqual([]);
  });
});

describe("formatTwinSearchSummary", () => {
  it("summarizes honesty", () => {
    const r = searchTwinSubstrate({
      query: "scaling",
      records: corpus,
    });
    expect(formatTwinSearchSummary(r)).toMatch(/remote_index_queried=false/);
  });
});
