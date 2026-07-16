/**
 * Marketplace free-before-buy HTML port residual over Midnight Oil + settings
 * (short residual: mktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack — FS 255; never purchase).
 * decision + competition DR + ND shadow twin presentation weekly pack (pure).
 *
 * Operator vision: pure reading — prefer free HTML digital book, seamless
 * account port intent only when ready; never auto-purchase; while MO
 * unattended price-ceiling + settings decision honesty remain pure.
 *
 * purchase_executed / hosted always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_execution_authorized / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
  type MarketplaceFreeBeforeBuyHtmlPortInput,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";
import {
  composeMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack,
  type MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose,
  type MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackInput,
} from "./moSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose";

export interface MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackInput {
  market: MarketplaceFreeBeforeBuyHtmlPortInput;
  mo_pack: Omit<
    MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose {
  title: string;
  account_id: string;
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  operator_id: string;
  focus_task: string;
  market: MarketplaceFreeBeforeBuyHtmlPortCompose;
  mo_pack: MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose;
  account_aligned: boolean;
  pack_ready: boolean;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
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
  record_persisted: false;
  remote_index_queried: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Free-before-buy HTML port stacked on MO + settings decision competition DR.
 * Never purchases; never hosts; never PDF-primary; ND REJECT.
 */
export function composeMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack(
  input: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackInput,
): MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.market || typeof input.market !== "object") {
    throw new Error("market must be an object");
  }
  if (!input.mo_pack || typeof input.mo_pack !== "object") {
    throw new Error("mo_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · hosted=false · pdf_view_authorized=false",
    "live_execution_authorized=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const market = composeMarketplaceFreeBeforeBuyHtmlPort(input.market);
  notes.push(...market.notes.map((n) => `[market] ${n}`));

  const mo_pack = composeMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21Mpack({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const title = requireNonEmpty(market.title, "title");
  const account_id = requireNonEmpty(market.account_id, "account_id");
  const week_id = requireNonEmpty(mo_pack.week_id, "week_id");
  const session_id = requireNonEmpty(mo_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    mo_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(mo_pack.asset_id, "asset_id");
  const operator_id = requireNonEmpty(mo_pack.operator_id, "operator_id");
  const focus_task = requireNonEmpty(mo_pack.focus_task, "focus_task");

  const account_aligned = mo_pack.account_id === account_id;
  if (!account_aligned) {
    notes.push(
      "account_id mismatch between market and mo_pack — pack_ready blocked",
    );
  } else {
    notes.push("account_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      account_aligned &&
      market.port_ready === true &&
      mo_pack.pack_ready === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      market.pdf_view_authorized === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.charge_executed === false &&
      mo_pack.secrets_stored === false &&
      mo_pack.inventory_mutated === false &&
      mo_pack.live_router_authorized === false &&
      mo_pack.live_dispatch_authorized === false &&
      mo_pack.remote_fetched === false &&
      mo_pack.twin_written === false &&
      mo_pack.pdf_primary === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      account_aligned &&
      input.operator_ack === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      mo_pack.live_execution_authorized === false &&
      (market.port_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — marketplace free-before-buy + MO settings decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market, mo_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    market.purchase_executed !== false ||
    market.hosted !== false ||
    market.pdf_view_authorized !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.charge_executed !== false ||
    mo_pack.secrets_stored !== false ||
    mo_pack.inventory_mutated !== false ||
    mo_pack.live_router_authorized !== false ||
    mo_pack.live_dispatch_authorized !== false ||
    mo_pack.remote_fetched !== false ||
    mo_pack.twin_written !== false ||
    mo_pack.pdf_primary !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
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
    title,
    account_id,
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    operator_id,
    focus_task,
    market,
    mo_pack,
    account_aligned,
    pack_ready,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
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
    record_persisted: false,
    remote_index_queried: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpack_compose_advisory",
  };
}

export function formatMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackSummary(
  c: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow21MpackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `port_ready=${c.market.port_ready} · ` +
    `path=${c.market.path} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `account_aligned=${c.account_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `purchase_executed=false · hosted=false · charge_executed=false`
  );
}
