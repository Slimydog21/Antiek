/**
 * Competition DR quality → write → twin substrate search/merge (pure).
 *
 * Operator vision: highest-quality competition-informed deep research folds
 * into write draft/analysis, then the derived twin note substrate is
 * intelligently searchable and cross-asset mergeable on the infinite
 * information platform — without live dispatch, remote index, or writes.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * draft_written / analysis_written / merge_executed always false.
 * remote_index_queried / twin_written / store_mutated always false.
 */

import {
  composeCompetitionDrQualityWrite,
  type CompetitionDrQualityWriteCompose,
  type CompetitionDrQualityWriteInput,
} from "./competitionDrQualityWriteCompose";
import {
  composeTwinSubstrateSearchMerge,
  type TwinSubstrateSearchMergeCompose,
} from "./twinSubstrateSearchMergeCompose";
import type { TwinSearchRecord } from "./recursiveTwinIntelligentSearch";

export interface CompetitionDrQualityWriteTwinSearchInput
  extends CompetitionDrQualityWriteInput {
  /** Query over competition-derived + optional extra twin corpus. */
  search_query: string;
  /** Optional additional twins for multi-parent merge / broader corpus. */
  extra_twin_records?: TwinSearchRecord[] | null;
  search_limit?: number;
  min_parents_for_merge?: number;
  /** Search pack id; defaults to `cqw-search-${session_id}`. */
  search_pack_id?: string | null;
  /**
   * When true (default), require quality_write.pack_ready AND
   * twin_search.pack_ready. When false, either path may ready the pack.
   */
  require_both_with_search?: boolean;
}

export interface CompetitionDrQualityWriteTwinSearchCompose {
  session_id: string;
  draft_id: string;
  parent_asset_id: string;
  quality_write: CompetitionDrQualityWriteCompose;
  twin_search: TwinSubstrateSearchMergeCompose;
  /** Derived corpus used for search (competition + extras). */
  twin_corpus: TwinSearchRecord[];
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  store_mutated: false;
  live_dispatched: false;
  notes: string[];
  authority: "competition_dr_quality_write_twin_search_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build twin search corpus from competition quality write pack.
 * Never invents competitor facts — only re-projects caller-supplied
 * decisions/citations and write-pack twin draft sections.
 */
function deriveTwinCorpus(
  parent_asset_id: string,
  quality_write: CompetitionDrQualityWriteCompose,
  extra: TwinSearchRecord[] | null | undefined,
): TwinSearchRecord[] {
  const records: TwinSearchRecord[] = [];
  const qs = quality_write.quality_source;
  const insights: string[] = [];
  const questions: string[] = [];

  for (const c of qs.citations.citations) {
    insights.push(c.title);
    records.push({
      twin_id: `twin-cite-${c.citation_id}`,
      parent_asset_id: `cite-parent-${c.citation_id}`,
      insights: [c.title],
      questions: [`How does "${c.title}" inform Antiek DR quality?`],
      source_label: c.family,
    });
  }

  for (const row of qs.competition.decisions) {
    if (row.antiek_status === "behind" && row.residual) {
      questions.push(row.residual);
      records.push({
        twin_id: `twin-gap-${row.competitor}-${row.area}`,
        parent_asset_id: `gap-parent-${row.competitor}-${row.area}`,
        insights: row.decision_summary ? [row.decision_summary] : [],
        questions: [row.residual],
        source_label: `${row.competitor}/${row.area}`,
      });
    } else if (row.decision_summary) {
      insights.push(
        `${row.competitor}/${row.area}: ${row.decision_summary}`,
      );
    }
  }

  // Primary twin for the parent asset (write substrate).
  if (insights.length === 0 && questions.length === 0) {
    questions.push("What competition gaps remain for Antiek DR quality?");
  }
  records.unshift({
    twin_id: `twin-${parent_asset_id}`,
    parent_asset_id,
    insights,
    questions,
    source_label: "competition_quality_write",
  });

  if (extra != null) {
    for (const r of extra) {
      records.push(r);
    }
  }

  return records;
}

/**
 * Compose competition quality→write with twin substrate search/merge.
 * Never dispatches, remote-indexes, or writes assets.
 */
export function composeCompetitionDrQualityWriteTwinSearch(
  input: CompetitionDrQualityWriteTwinSearchInput,
): CompetitionDrQualityWriteTwinSearchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const draft_id = requireNonEmpty(input.draft_id, "draft_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  const search_query = requireNonEmpty(input.search_query, "search_query");

  const require_both_with_search =
    input.require_both_with_search === undefined
      ? true
      : input.require_both_with_search;
  if (typeof require_both_with_search !== "boolean") {
    throw new Error("require_both_with_search must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "draft_written=false · analysis_written=false · merge_executed=false",
    "remote_index_queried=false · twin_written=false · store_mutated=false",
    "live_dispatched=false",
  ];

  const quality_write = composeCompetitionDrQualityWrite({
    session_id: input.session_id,
    draft_id: input.draft_id,
    parent_asset_id: input.parent_asset_id,
    competitor_decisions: input.competitor_decisions,
    focus_areas: input.focus_areas,
    requested_families: input.requested_families,
    citations: input.citations,
    filter_to_selected_families: input.filter_to_selected_families,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    operator_ack: input.operator_ack,
    require_no_behind_gaps: input.require_no_behind_gaps,
    analysis_kind: input.analysis_kind,
    twin_slices: input.twin_slices,
    chase_slots: input.chase_slots,
    base_draft_html: input.base_draft_html,
    extra_write_findings: input.extra_write_findings,
    require_both_with_write: input.require_both_with_write,
  });
  notes.push(...quality_write.notes.map((n) => `[quality_write] ${n}`));

  const twin_corpus = deriveTwinCorpus(
    parent_asset_id,
    quality_write,
    input.extra_twin_records,
  );
  notes.push(`twin_corpus_size=${twin_corpus.length}`);

  const search_pack_id =
    input.search_pack_id != null && String(input.search_pack_id).trim()
      ? String(input.search_pack_id).trim()
      : `cqw-search-${session_id}`;

  const twin_search = composeTwinSubstrateSearchMerge({
    pack_id: search_pack_id,
    search_query,
    twin_records: twin_corpus,
    search_limit: input.search_limit,
    min_parents_for_merge: input.min_parents_for_merge,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_search.notes.map((n) => `[twin_search] ${n}`));

  let pack_ready = false;
  if (require_both_with_search) {
    pack_ready =
      quality_write.pack_ready === true &&
      twin_search.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (quality_write.pack_ready === true || twin_search.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition quality write + twin search ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — quality_write, twin_search, or operator_ack gate open",
    );
  }

  if (
    quality_write.live_dispatch_authorized !== false ||
    quality_write.remote_fetched !== false ||
    quality_write.backlog_mutated !== false ||
    quality_write.draft_written !== false ||
    quality_write.analysis_written !== false ||
    quality_write.merge_executed !== false ||
    twin_search.remote_index_queried !== false ||
    twin_search.merge_executed !== false ||
    twin_search.twin_written !== false ||
    twin_search.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("store_mutated=false");
  notes.push("live_dispatched=false");

  return {
    session_id,
    draft_id,
    parent_asset_id,
    quality_write,
    twin_search,
    twin_corpus,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    store_mutated: false,
    live_dispatched: false,
    notes,
    authority: "competition_dr_quality_write_twin_search_compose_advisory",
  };
}

export function formatCompetitionDrQualityWriteTwinSearchSummary(
  c: CompetitionDrQualityWriteTwinSearchCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `quality_write_ready=${c.quality_write.pack_ready} · ` +
    `twin_search_ready=${c.twin_search.pack_ready} · ` +
    `hits=${c.twin_search.search.hits.length} · ` +
    `corpus=${c.twin_corpus.length} · ` +
    `live_dispatch_authorized=false · remote_index_queried=false · ` +
    `draft_written=false · merge_executed=false · twin_written=false`
  );
}
