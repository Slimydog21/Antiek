/**
 * Twin substrate intelligent search → cross-asset merge compose (pure).
 *
 * Operator vision: search insights/questions across the twin note substrate,
 * then propose merging selected twin slices across assets for combining
 * contexts on the infinite information platform.
 *
 * remote_index_queried always false.
 * merge_executed always false.
 * twin_written always false.
 * store_mutated always false.
 */

import {
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "./recursiveTwinIntelligentSearch";
import {
  composeTwinSubstrateCrossAssetMerge,
  type TwinSubstrateCrossAssetMergeCompose,
  type TwinSubstrateSlice,
} from "./twinSubstrateCrossAssetMergeCompose";

export interface TwinSubstrateSearchMergeInput {
  pack_id: string;
  search_query: string;
  /** Full twin corpus (caller-supplied). */
  twin_records: TwinSearchRecord[];
  search_limit?: number;
  /**
   * Minimum distinct parents among hits to attempt merge.
   * Default 2. When fewer parents match, merge is skipped (soft).
   */
  min_parents_for_merge?: number;
  operator_ack: boolean;
}

export interface TwinSubstrateSearchMergeCompose {
  pack_id: string;
  search: TwinSearchResult;
  merge: TwinSubstrateCrossAssetMergeCompose | null;
  /**
   * True when search composed and (merge ready when ≥min parents, or
   * search-only ready with hits). Still never writes/merges.
   */
  pack_ready: boolean;
  remote_index_queried: false;
  merge_executed: false;
  twin_written: false;
  store_mutated: false;
  notes: string[];
  authority: "twin_substrate_search_merge_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Map search hits back to twin slices for cross-asset merge.
 * Uses only hit twins present in corpus — never invents insights/questions.
 */
function hitsToSlices(
  hits: TwinSearchResult["hits"],
  corpus: TwinSearchRecord[],
): TwinSubstrateSlice[] {
  const byId = new Map(corpus.map((r) => [r.twin_id, r]));
  const slices: TwinSubstrateSlice[] = [];
  const seenParent = new Set<string>();
  for (const hit of hits) {
    const rec = byId.get(hit.twin_id);
    if (!rec) continue;
    if (seenParent.has(rec.parent_asset_id)) {
      // merge compose wants distinct parents; keep first hit per parent
      continue;
    }
    seenParent.add(rec.parent_asset_id);
    slices.push({
      parent_asset_id: rec.parent_asset_id,
      twin_asset_id: rec.twin_id,
      insights: rec.insights,
      questions: rec.questions,
    });
  }
  return slices;
}

/**
 * Search twin substrate then propose cross-asset merge of hit twins.
 * Never remote-indexes; never merges or writes twins.
 */
export function composeTwinSubstrateSearchMerge(
  input: TwinSubstrateSearchMergeInput,
): TwinSubstrateSearchMergeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const pack_id = requireNonEmpty(input.pack_id, "pack_id");
  if (!Array.isArray(input.twin_records)) {
    throw new Error("twin_records must be an array");
  }

  const min_parents =
    input.min_parents_for_merge === undefined ||
    input.min_parents_for_merge === null
      ? 2
      : input.min_parents_for_merge;
  if (
    typeof min_parents !== "number" ||
    !Number.isInteger(min_parents) ||
    min_parents < 2
  ) {
    throw new Error("min_parents_for_merge must be integer ≥ 2");
  }

  const notes: string[] = [
    "remote_index_queried=false — pure local twin corpus scan",
    "merge_executed=false — cross-asset merge is intent only",
    "twin_written=false · store_mutated=false",
  ];

  const search = searchTwinSubstrate({
    query: input.search_query,
    records: input.twin_records,
    limit: input.search_limit,
  });
  notes.push(...search.notes.map((n) => `[search] ${n}`));
  notes.push(`search_hits=${search.hits.length}`);

  let merge: TwinSubstrateCrossAssetMergeCompose | null = null;
  const slices = hitsToSlices(search.hits, input.twin_records);
  notes.push(`distinct_parent_slices_from_hits=${slices.length}`);

  if (slices.length >= min_parents) {
    merge = composeTwinSubstrateCrossAssetMerge({
      pack_id,
      slices,
      operator_ack: input.operator_ack,
    });
    notes.push(...merge.notes.map((n) => `[merge] ${n}`));
  } else if (search.hits.length > 0) {
    notes.push(
      `merge skipped — need ≥${min_parents} distinct parents among hits (got ${slices.length})`,
    );
  } else {
    notes.push("merge skipped — no search hits");
  }

  const pack_ready =
    input.operator_ack === true &&
    (merge !== null
      ? merge.merge_ready === true
      : search.hits.length > 0); // search-only ready when hits exist but <2 parents

  if (pack_ready) {
    notes.push(
      merge
        ? "pack_ready=true — search+merge intent ready; still pure"
        : "pack_ready=true — search hits ready (merge deferred, insufficient parents)",
    );
  } else {
    notes.push(
      "pack_ready=false — no hits, merge not ready, or operator_ack missing",
    );
  }

  if (
    search.remote_index_queried !== false ||
    (merge != null &&
      (merge.merge_executed !== false ||
        merge.twin_written !== false ||
        merge.store_mutated !== false))
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_index_queried=false");
  notes.push("merge_executed=false");
  notes.push("twin_written=false");
  notes.push("store_mutated=false");

  return {
    pack_id,
    search,
    merge,
    pack_ready,
    remote_index_queried: false,
    merge_executed: false,
    twin_written: false,
    store_mutated: false,
    notes,
    authority: "twin_substrate_search_merge_compose_advisory",
  };
}

export function formatTwinSubstrateSearchMergeSummary(
  c: TwinSubstrateSearchMergeCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · hits=${c.search.hits.length} · ` +
    `merge_ready=${c.merge?.merge_ready ?? false} · ` +
    `remote_index_queried=false · merge_executed=false · twin_written=false`
  );
}
