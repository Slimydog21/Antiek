/**
 * Twin intelligent search surface over Antiek-bench weekly + HTML-native
 * recursive twin pack (pure).
 *
 * Operator vision: intelligent search over the twin substrate of the infinite
 * information platform, surfaced beside weekly bench learn + HTML-native
 * workstation honesty — without remote index, twin writes, or bench mutation.
 *
 * remote_index_queried always false.
 * backlog_mutated / store_mutated / suite_rewritten always false.
 * pdf_view_authorized / pdf_primary always false.
 * twin_written / secrets_stored / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "./recursiveTwinIntelligentSearch";
import {
  composeAntiekBenchWeeklyHtmlNativeRecursiveTwin,
  type AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose,
  type AntiekBenchWeeklyHtmlNativeRecursiveTwinInput,
} from "./antiekBenchWeeklyHtmlNativeRecursiveTwinCompose";

export interface TwinSearchAntiekBenchWeeklyHtmlNativeInput {
  search_query: string;
  twin_records: TwinSearchRecord[];
  search_limit?: number;
  weekly_html: Omit<
    AntiekBenchWeeklyHtmlNativeRecursiveTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require ≥1 search hit AND weekly_html.pack_ready.
   */
  require_both?: boolean;
}

export interface TwinSearchAntiekBenchWeeklyHtmlNativeCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  search: TwinSearchResult;
  weekly_html: AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose;
  pack_ready: boolean;
  hit_count: number;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  notes: string[];
  authority: "twin_search_antiek_bench_weekly_html_native_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Twin substrate search stacked on weekly bench + HTML-native recursive twin.
 * Never remote-indexes; never mutates bench; never PDF-primary; ND REJECT.
 */
export function composeTwinSearchAntiekBenchWeeklyHtmlNative(
  input: TwinSearchAntiekBenchWeeklyHtmlNativeInput,
): TwinSearchAntiekBenchWeeklyHtmlNativeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.weekly_html || typeof input.weekly_html !== "object") {
    throw new Error("weekly_html must be an object");
  }
  if (!Array.isArray(input.twin_records)) {
    throw new Error("twin_records must be an array");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "remote_index_queried=false — pure substrate scan only",
    "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "twin_written=false · secrets_stored=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const search = searchTwinSubstrate({
    query: input.search_query,
    records: input.twin_records,
    limit: input.search_limit,
  });
  notes.push(...search.notes.map((n) => `[search] ${n}`));

  const weekly_html = composeAntiekBenchWeeklyHtmlNativeRecursiveTwin({
    ...input.weekly_html,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_html.notes.map((n) => `[weekly_html] ${n}`));

  const week_id = requireNonEmpty(weekly_html.week_id, "week_id");
  const session_id = requireNonEmpty(weekly_html.session_id, "session_id");
  const asset_id = requireNonEmpty(weekly_html.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    weekly_html.parent_asset_id,
    "parent_asset_id",
  );
  const hit_count = search.hits.length;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      hit_count >= 1 &&
      weekly_html.pack_ready === true &&
      search.remote_index_queried === false &&
      weekly_html.backlog_mutated === false &&
      weekly_html.store_mutated === false &&
      weekly_html.suite_rewritten === false &&
      weekly_html.production_router_verdict === "REJECT" &&
      weekly_html.pdf_view_authorized === false &&
      weekly_html.pdf_primary === false &&
      weekly_html.twin_written === false &&
      weekly_html.secrets_stored === false &&
      weekly_html.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      search.remote_index_queried === false &&
      weekly_html.production_router_verdict === "REJECT" &&
      weekly_html.pdf_primary === false &&
      (hit_count >= 1 || weekly_html.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin search + weekly HTML-native recursive twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — search hits, weekly_html, or operator_ack gate open",
    );
  }

  if (
    search.remote_index_queried !== false ||
    weekly_html.backlog_mutated !== false ||
    weekly_html.store_mutated !== false ||
    weekly_html.suite_rewritten !== false ||
    weekly_html.pdf_view_authorized !== false ||
    weekly_html.pdf_primary !== false ||
    weekly_html.twin_written !== false ||
    weekly_html.secrets_stored !== false ||
    weekly_html.charge_executed !== false ||
    weekly_html.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    search,
    weekly_html,
    pack_ready,
    hit_count,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    notes,
    authority:
      "twin_search_antiek_bench_weekly_html_native_compose_advisory",
  };
}

export function formatTwinSearchAntiekBenchWeeklyHtmlNativeSummary(
  c: TwinSearchAntiekBenchWeeklyHtmlNativeCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `hits=${c.hit_count} · ` +
    `weekly_ready=${c.weekly_html.pack_ready} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_index_queried=false · suite_rewritten=false · pdf_primary=false`
  );
}
