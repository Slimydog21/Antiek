/**
 * Midnight Oil price-ceiling residual re-entry over marketplace free-before-buy
 * (short residual: moMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27Mpack — FS 255; never live-executes MO).
 * stacked on mkt residual Mow26 + settings/competition/ND honesty (pure).
 *
 * Operator vision: unattended deep research with recommended price ceiling to
 * approve, beside free marketplace HTML port intent — never charges, never
 * purchases, never stores secrets, ND REJECT.
 *
 * live_execution_authorized / charge_executed always false.
 * purchase_executed / hosted / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMidnightOilPriceCeilingApproval,
  type MidnightOilPriceCeilingApprovalCompose,
  type MidnightOilPriceCeilingApprovalInput,
} from "./midnightOilPriceCeilingApprovalCompose";
import {
  composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26Mpack,
  type MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26MpackCompose,
  type MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26MpackInput,
} from "./mktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26MpackCompose";

export interface MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackInput {
  mo: Omit<MidnightOilPriceCeilingApprovalInput, "operator_ack">;
  mkt_pack: Omit<MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26MpackInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  operator_id: string;
  focus_task: string;
  mo: MidnightOilPriceCeilingApprovalCompose;
  mkt_pack: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26MpackCompose;
  account_aligned: boolean;
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_index_queried: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Midnight Oil price-ceiling re-entry stacked on marketplace free residual.
 * Never live-executes; never charges; never purchases; ND REJECT.
 */
export function composeMoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27Mpack(
  input: MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackInput,
): MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.mkt_pack || typeof input.mkt_pack !== "object") {
    throw new Error("mkt_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false · charge_executed=false",
    "purchase_executed=false · hosted=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilPriceCeilingApproval({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const mkt_pack = composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow26Mpack({
    ...input.mkt_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mkt_pack.notes.map((n) => `[mkt_pack] ${n}`));

  const operator_id = requireNonEmpty(mo.operator_id, "operator_id");
  const week_id = requireNonEmpty(mkt_pack.week_id, "week_id");
  const session_id = requireNonEmpty(mkt_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    mkt_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(mkt_pack.asset_id, "asset_id");
  const title = requireNonEmpty(mkt_pack.title, "title");
  const account_id = requireNonEmpty(mkt_pack.account_id, "account_id");
  const focus_task = requireNonEmpty(mkt_pack.focus_task, "focus_task");

  const account_aligned = mkt_pack.account_id === account_id;
  if (!account_aligned) {
    notes.push("account_id mismatch — pack_ready blocked");
  } else {
    notes.push("account_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      account_aligned &&
      mo.pack_ready === true &&
      mkt_pack.pack_ready === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      mkt_pack.purchase_executed === false &&
      mkt_pack.hosted === false &&
      mkt_pack.pdf_view_authorized === false &&
      mkt_pack.pdf_primary === false &&
      mkt_pack.live_execution_authorized === false &&
      mkt_pack.charge_executed === false &&
      mkt_pack.secrets_stored === false &&
      mkt_pack.inventory_mutated === false &&
      mkt_pack.live_router_authorized === false &&
      mkt_pack.live_dispatch_authorized === false &&
      mkt_pack.remote_fetched === false &&
      mkt_pack.twin_written === false &&
      mkt_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      account_aligned &&
      input.operator_ack === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      mkt_pack.purchase_executed === false &&
      mkt_pack.production_router_verdict === "REJECT" &&
      (mo.pack_ready === true || mkt_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — Midnight Oil price-ceiling + marketplace free residual ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, mkt_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    mo.charge_executed !== false ||
    mkt_pack.purchase_executed !== false ||
    mkt_pack.hosted !== false ||
    mkt_pack.pdf_view_authorized !== false ||
    mkt_pack.pdf_primary !== false ||
    mkt_pack.live_execution_authorized !== false ||
    mkt_pack.charge_executed !== false ||
    mkt_pack.secrets_stored !== false ||
    mkt_pack.inventory_mutated !== false ||
    mkt_pack.live_router_authorized !== false ||
    mkt_pack.live_dispatch_authorized !== false ||
    mkt_pack.remote_fetched !== false ||
    mkt_pack.twin_written !== false ||
    mkt_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    operator_id,
    focus_task,
    mo,
    mkt_pack,
    account_aligned,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_index_queried: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpack_compose_advisory",
  };
}

export function formatMoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackSummary(
  c: MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow27MpackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.pack_ready} · ` +
    `ceiling_approved=${c.mo.ceiling_approved} · ` +
    `mkt_ready=${c.mkt_pack.pack_ready} · ` +
    `stage=${c.mo.stage} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · charge_executed=false · purchase_executed=false`
  );
}
