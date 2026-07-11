import { describe, expect, it } from "vitest";
import {
  composeTwinSubstrateSearchMerge,
  formatTwinSubstrateSearchMergeSummary,
} from "./twinSubstrateSearchMergeCompose";

const corpus = [
  {
    twin_id: "twin-1",
    parent_asset_id: "asset-1",
    insights: ["scaling laws hold under compute-optimal regimes"],
    questions: ["Does the law break at sparse models?"],
  },
  {
    twin_id: "twin-2",
    parent_asset_id: "asset-2",
    insights: ["attention efficiency tradeoffs with scaling"],
    questions: ["What is the scaling frontier?"],
  },
  {
    twin_id: "twin-3",
    parent_asset_id: "asset-3",
    insights: ["unrelated gardening notes"],
    questions: ["How wet should soil be?"],
  },
];

describe("composeTwinSubstrateSearchMerge", () => {
  it("search hits across parents → merge ready", () => {
    const c = composeTwinSubstrateSearchMerge({
      pack_id: "pack-1",
      search_query: "scaling laws",
      twin_records: corpus,
      operator_ack: true,
    });
    expect(c.search.hits.length).toBeGreaterThanOrEqual(2);
    expect(c.merge).not.toBeNull();
    expect(c.merge!.merge_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.remote_index_queried).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "twin_substrate_search_merge_compose_advisory",
    );
    expect(formatTwinSubstrateSearchMergeSummary(c)).toMatch(
      /merge_executed=false/,
    );
  });

  it("single-parent hits skip merge but pack may still ready", () => {
    const c = composeTwinSubstrateSearchMerge({
      pack_id: "pack-2",
      search_query: "gardening soil",
      twin_records: corpus,
      operator_ack: true,
    });
    expect(c.search.hits.length).toBeGreaterThan(0);
    expect(c.merge).toBeNull();
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });

  it("no hits not pack_ready", () => {
    const c = composeTwinSubstrateSearchMerge({
      pack_id: "pack-3",
      search_query: "zzzznonexistenttoken",
      twin_records: corpus,
      operator_ack: true,
    });
    expect(c.search.hits.length).toBe(0);
    expect(c.merge).toBeNull();
    expect(c.pack_ready).toBe(false);
    expect(c.remote_index_queried).toBe(false);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeTwinSubstrateSearchMerge({
      pack_id: "pack-4",
      search_query: "scaling",
      twin_records: corpus,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.twin_written).toBe(false);
  });
});
