/**
 * Twin intelligent search overlay on competition DR + ND shadow weekly
 * marketplace pack (pure).
 *
 * Operator vision: every information asset twin substrate (insights +
 * questions from competition gaps, arxiv/substack citations, and optional
 * extra twins) is intelligently searchable and cross-asset mergeable on the
 * infinite information platform — without live dispatch, remote index, or
 * twin writes. Stacks on competition quality + ND §16 REJECT + Antiek-bench
 * weekly + free marketplace honesty.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * remote_index_queried / merge_executed / twin_written always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 * purchase_executed / hosted / store_mutated always false.
 */

import {
  composeCompetitionDrNdShadowWeeklyMarketplace,
  type CompetitionDrNdShadowWeeklyMarketplaceCompose,
  type CompetitionDrNdShadowWeeklyMarketplaceInput,
} from "./competitionDrNdShadowWeeklyMarketplaceCompose";
import {
  composeTwinSubstrateSearchMerge,
  type TwinSubstrateSearchMergeCompose,
} from "./twinSubstrateSearchMergeCompose";
import type { TwinSearchRecord } from "./recursiveTwinIntelligentSearch";

export interface TwinSearchCompetitionDrNdShadowWeeklyMarketplaceInput {
  competition_pack: Omit<
    CompetitionDrNdShadowWeeklyMarketplaceInput,
    "operator_ack"
  >;
  search_query: string;
  /** Optional additional twins for multi-parent merge / broader corpus. */
  extra_twin_records?: TwinSearchRecord[] | null;
  search_limit?: number;
  min_parents_for_merge?: number;
  /** Search pack id; defaults to `twin-search-cdnwm-${session_id}`. */
  search_pack_id?: string | null;
  operator_ack: boolean;
  /**
   * When true (default), require competition_pack.pack_ready AND
   * twin_search.pack_ready. When false, either path may ready the pack.
   */
  require_both?: boolean;
}

export interface TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose {
  session_id: string;
  week_id: string;
  parent_asset_id: string;
  competition_pack: CompetitionDrNdShadowWeeklyMarketplaceCompose;
  twin_search: TwinSubstrateSearchMergeCompose;
  /** Derived corpus used for search (competition + extras). */
  twin_corpus: TwinSearchRecord[];
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  store_mutated: false;
  purchase_executed: false;
  hosted: false;
  remote_index_queried: false;
  merge_executed: false;
  twin_written: false;
  prompts_injected: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  record_persisted: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  notes: string[];
  authority: "twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build twin search corpus from competition DR ND weekly pack.
 * Never invents competitor facts — only re-projects caller-supplied
 * decisions/citations from the composed competition quality source pack.
 */
function deriveTwinCorpus(
  parent_asset_id: string,
  pack: CompetitionDrNdShadowWeeklyMarketplaceCompose,
  extra: TwinSearchRecord[] | null | undefined,
): TwinSearchRecord[] {
  const records: TwinSearchRecord[] = [];
  const qs = pack.competition;
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

  // Primary twin for the parent asset (competition pack substrate).
  if (insights.length === 0 && questions.length === 0) {
    questions.push("What competition gaps remain for Antiek DR quality?");
  }
  records.unshift({
    twin_id: `twin-${parent_asset_id}`,
    parent_asset_id,
    insights,
    questions,
    source_label: "competition_dr_nd_shadow_weekly_marketplace",
  });

  if (extra != null) {
    for (const r of extra) {
      records.push(r);
    }
  }

  return records;
}

/**
 * Competition DR + ND weekly marketplace with twin intelligent search overlay.
 * Never live-dispatches, remote-indexes, production-routes, or writes twins.
 */
export function composeTwinSearchCompetitionDrNdShadowWeeklyMarketplace(
  input: TwinSearchCompetitionDrNdShadowWeeklyMarketplaceInput,
): TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition_pack || typeof input.competition_pack !== "object") {
    throw new Error("competition_pack must be an object");
  }
  const search_query = requireNonEmpty(input.search_query, "search_query");

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "remote_index_queried=false · merge_executed=false · twin_written=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
    "purchase_executed=false · hosted=false · store_mutated=false",
  ];

  const competition_pack = composeCompetitionDrNdShadowWeeklyMarketplace({
    ...input.competition_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition_pack.notes.map((n) => `[competition_pack] ${n}`));

  const session_id = requireNonEmpty(competition_pack.session_id, "session_id");
  const week_id = requireNonEmpty(competition_pack.week_id, "week_id");
  const parent_asset_id = requireNonEmpty(
    competition_pack.parent_asset_id,
    "parent_asset_id",
  );

  const twin_corpus = deriveTwinCorpus(
    parent_asset_id,
    competition_pack,
    input.extra_twin_records,
  );
  notes.push(`twin_corpus_size=${twin_corpus.length}`);

  const search_pack_id =
    input.search_pack_id != null && String(input.search_pack_id).trim()
      ? String(input.search_pack_id).trim()
      : `twin-search-cdnwm-${session_id}`;

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
  if (require_both) {
    pack_ready =
      competition_pack.pack_ready === true &&
      twin_search.pack_ready === true &&
      competition_pack.production_router_verdict === "REJECT" &&
      competition_pack.live_dispatch_authorized === false &&
      competition_pack.remote_fetched === false &&
      twin_search.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      competition_pack.production_router_verdict === "REJECT" &&
      twin_search.remote_index_queried === false &&
      (competition_pack.pack_ready === true || twin_search.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin intelligent search over competition DR ND weekly pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition_pack, twin_search, or operator_ack gate open",
    );
  }

  if (
    competition_pack.live_dispatch_authorized !== false ||
    competition_pack.remote_fetched !== false ||
    competition_pack.backlog_mutated !== false ||
    competition_pack.production_router_verdict !== "REJECT" ||
    competition_pack.live_router_authorized !== false ||
    competition_pack.purchase_executed !== false ||
    competition_pack.hosted !== false ||
    competition_pack.store_mutated !== false ||
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
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("store_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_index_queried=false");
  notes.push("merge_executed=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("record_persisted=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    week_id,
    parent_asset_id,
    competition_pack,
    twin_search,
    twin_corpus,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    store_mutated: false,
    purchase_executed: false,
    hosted: false,
    remote_index_queried: false,
    merge_executed: false,
    twin_written: false,
    prompts_injected: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    record_persisted: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    notes,
    authority:
      "twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_advisory",
  };
}

export function formatTwinSearchCompetitionDrNdShadowWeeklyMarketplaceSummary(
  c: TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `competition_pack_ready=${c.competition_pack.pack_ready} · ` +
    `twin_search_ready=${c.twin_search.pack_ready} · ` +
    `hits=${c.twin_search.search.hits.length} · ` +
    `corpus=${c.twin_corpus.length} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_index_queried=false · ` +
    `merge_executed=false · twin_written=false`
  );
}
