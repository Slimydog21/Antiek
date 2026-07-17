/**
 * Write-mode twin collective analysis residual over fullscreen-open +
 * draft-before-merge collective FDR MD twin-search HTML-native mow12 (pure).
 * Short moniker Mow12 (NAME_MAX-safe).
 *
 * Operator vision: after multi-agent floating researches complete, merge twin
 * substrate + completed chases into written analysis while fullscreen view +
 * provisional draft-before-merge + collective multiselect + floating DR +
 * workstation records remain pure — never writes analysis/draft, never live-dispatches.
 *
 * draft_written / analysis_written / merge_executed always false.
 * live_dispatched / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeWriteModeTwinCollectiveAnalysis,
  type WriteModeTwinCollectiveAnalysisCompose,
  type WriteModeTwinCollectiveAnalysisInput,
} from "./writeModeTwinCollectiveAnalysisCompose";
import {
  composeFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23Mpack,
  type FsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose,
  type FsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackInput,
} from "./fsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose";

export interface WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackInput {
  write: Omit<WriteModeTwinCollectiveAnalysisInput, "operator_ack">;
  fullscreen_pack: Omit<FsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  write: WriteModeTwinCollectiveAnalysisCompose;
  fullscreen_pack: FsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Write twin collective analysis stacked on fullscreen draft-before-merge
 * collective FDR MD mow12. Never writes analysis/draft; ND REJECT.
 */
export function composeWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23Mpack(
  input: WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackInput,
): WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.write || typeof input.write !== "object") {
    throw new Error("write must be an object");
  }
  if (!input.fullscreen_pack || typeof input.fullscreen_pack !== "object") {
    throw new Error("fullscreen_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · analysis_written=false · merge_executed=false",
    "live_dispatched=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const write = composeWriteModeTwinCollectiveAnalysis({
    ...input.write,
    operator_ack: input.operator_ack,
  });
  notes.push(...write.notes.map((n) => `[write] ${n}`));

  const fullscreen_pack = composeFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23Mpack({
    ...input.fullscreen_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen_pack.notes.map((n) => `[fullscreen_pack] ${n}`));

  const week_id = requireNonEmpty(fullscreen_pack.week_id, "week_id");
  const session_id = requireNonEmpty(write.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    write.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(fullscreen_pack.asset_id, "asset_id");
  const title = requireNonEmpty(fullscreen_pack.title, "title");
  const account_id = requireNonEmpty(fullscreen_pack.account_id, "account_id");

  const session_aligned = fullscreen_pack.session_id === session_id;
  const parent_aligned =
    fullscreen_pack.parent_asset_id === parent_asset_id ||
    fullscreen_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      `session_aligned=false — write.session_id=${session_id} fullscreen_pack.session_id=${fullscreen_pack.session_id}`,
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      `parent_aligned=false — write.parent=${parent_asset_id} fullscreen_pack.parent=${fullscreen_pack.parent_asset_id} asset=${fullscreen_pack.asset_id}`,
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      write.pack_ready === true &&
      fullscreen_pack.pack_ready === true &&
      write.draft_written === false &&
      write.analysis_written === false &&
      write.merge_executed === false &&
      write.live_dispatched === false &&
      fullscreen_pack.live_dispatched === false &&
      fullscreen_pack.pack_dispatched === false &&
      fullscreen_pack.merge_executed === false &&
      fullscreen_pack.draft_written === false &&
      fullscreen_pack.analysis_written === false &&
      fullscreen_pack.record_persisted === false &&
      fullscreen_pack.prompts_injected === false &&
      fullscreen_pack.live_router_authorized === false &&
      fullscreen_pack.secrets_stored === false &&
      fullscreen_pack.remote_index_queried === false &&
      fullscreen_pack.twin_written === false &&
      fullscreen_pack.purchase_executed === false &&
      fullscreen_pack.hosted === false &&
      fullscreen_pack.pdf_primary === false &&
      fullscreen_pack.live_execution_authorized === false &&
      fullscreen_pack.charge_executed === false &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      input.operator_ack === true &&
      write.draft_written === false &&
      write.analysis_written === false &&
      write.live_dispatched === false &&
      fullscreen_pack.live_dispatched === false &&
      fullscreen_pack.production_router_verdict === "REJECT" &&
      fullscreen_pack.pdf_primary === false &&
      fullscreen_pack.live_router_authorized === false &&
      (write.pack_ready === true || fullscreen_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — write twin collective + fullscreen draft-before-merge collective FDR MD mow12 ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — write, fullscreen_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    write.draft_written !== false ||
    write.analysis_written !== false ||
    write.merge_executed !== false ||
    write.live_dispatched !== false ||
    fullscreen_pack.live_dispatched !== false ||
    fullscreen_pack.pack_dispatched !== false ||
    fullscreen_pack.merge_executed !== false ||
    fullscreen_pack.draft_written !== false ||
    fullscreen_pack.analysis_written !== false ||
    fullscreen_pack.record_persisted !== false ||
    fullscreen_pack.prompts_injected !== false ||
    fullscreen_pack.live_router_authorized !== false ||
    fullscreen_pack.secrets_stored !== false ||
    fullscreen_pack.remote_index_queried !== false ||
    fullscreen_pack.twin_written !== false ||
    fullscreen_pack.purchase_executed !== false ||
    fullscreen_pack.hosted !== false ||
    fullscreen_pack.pdf_primary !== false ||
    fullscreen_pack.live_execution_authorized !== false ||
    fullscreen_pack.charge_executed !== false ||
    fullscreen_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    write,
    fullscreen_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpack_compose_advisory",
  };
}

export function formatWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackSummary(
  c: WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `write_ready=${c.write.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · analysis_written=false · live_dispatched=false`
  );
}
