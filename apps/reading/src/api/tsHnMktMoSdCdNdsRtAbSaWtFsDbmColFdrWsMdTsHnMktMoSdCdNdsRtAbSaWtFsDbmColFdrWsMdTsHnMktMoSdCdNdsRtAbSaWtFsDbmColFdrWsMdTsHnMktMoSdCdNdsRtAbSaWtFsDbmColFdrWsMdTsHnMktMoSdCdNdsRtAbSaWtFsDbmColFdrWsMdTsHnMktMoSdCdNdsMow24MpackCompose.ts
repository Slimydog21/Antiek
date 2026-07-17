/**
 * Twin intelligent search residual over HTML-native marketplace free residual
 * (short residual: tsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24Mpack — FS 255).
 *
 * Operator vision: intelligent search over the twin substrate of the infinite
 * information platform, surfaced beside HTML-native view + free-before-buy
 * marketplace + Midnight Oil + settings decision honesty — without remote
 * index, twin writes, or purchase.
 *
 * remote_index_queried always false.
 * twin_written / purchase_executed / hosted always false.
 * pdf_view_authorized / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "./recursiveTwinIntelligentSearch";
import {
  composeHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24Mpack,
  type HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose,
  type HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackInput,
} from "./hnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose";

export interface TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackInput {
  search_query: string;
  twin_records: TwinSearchRecord[];
  search_limit?: number;
  html_pack: Omit<
    HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require ≥1 search hit AND html_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  search: TwinSearchResult;
  html_pack: HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose;
  pack_ready: boolean;
  hit_count: number;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_fetched: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Twin substrate search stacked on HTML-native marketplace free residual.
 * Never queries remote index; never writes twins; ND REJECT.
 */
export function composeTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24Mpack(
  input: TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackInput,
): TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.html_pack || typeof input.html_pack !== "object") {
    throw new Error("html_pack must be an object");
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
    "twin_written=false · purchase_executed=false · hosted=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const search = searchTwinSubstrate({
    query: input.search_query,
    records: input.twin_records,
    limit: input.search_limit,
  });
  notes.push(...search.notes.map((n) => `[search] ${n}`));

  const html_pack = composeHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24Mpack({
    ...input.html_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_pack.notes.map((n) => `[html_pack] ${n}`));

  const week_id = requireNonEmpty(html_pack.week_id, "week_id");
  const session_id = requireNonEmpty(html_pack.session_id, "session_id");
  const asset_id = requireNonEmpty(html_pack.asset_id, "asset_id");
  const parent_asset_id = requireNonEmpty(
    html_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(html_pack.title, "title");
  const account_id = requireNonEmpty(html_pack.account_id, "account_id");
  const hit_count = search.hits.length;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      hit_count >= 1 &&
      html_pack.pack_ready === true &&
      search.remote_index_queried === false &&
      html_pack.pdf_view_authorized === false &&
      html_pack.pdf_primary === false &&
      html_pack.purchase_executed === false &&
      html_pack.hosted === false &&
      html_pack.twin_written === false &&
      html_pack.live_execution_authorized === false &&
      html_pack.charge_executed === false &&
      html_pack.remote_fetched === false &&
      html_pack.secrets_stored === false &&
      html_pack.live_router_authorized === false &&
      html_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      search.remote_index_queried === false &&
      html_pack.production_router_verdict === "REJECT" &&
      html_pack.pdf_primary === false &&
      html_pack.purchase_executed === false &&
      (hit_count >= 1 || html_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin search + HTML-native marketplace free residual ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — search hits, html_pack, or operator_ack gate open",
    );
  }

  if (
    search.remote_index_queried !== false ||
    html_pack.pdf_view_authorized !== false ||
    html_pack.pdf_primary !== false ||
    html_pack.purchase_executed !== false ||
    html_pack.hosted !== false ||
    html_pack.twin_written !== false ||
    html_pack.live_execution_authorized !== false ||
    html_pack.charge_executed !== false ||
    html_pack.remote_fetched !== false ||
    html_pack.secrets_stored !== false ||
    html_pack.live_router_authorized !== false ||
    html_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    search,
    html_pack,
    pack_ready,
    hit_count,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_fetched: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpack_compose_advisory",
  };
}

export function formatTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackSummary(
  c: TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow24MpackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `hits=${c.hit_count} · ` +
    `html_ready=${c.html_pack.pack_ready} · ` +
    `query=${c.search.query} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `remote_index_queried=false · twin_written=false · purchase_executed=false`
  );
}
