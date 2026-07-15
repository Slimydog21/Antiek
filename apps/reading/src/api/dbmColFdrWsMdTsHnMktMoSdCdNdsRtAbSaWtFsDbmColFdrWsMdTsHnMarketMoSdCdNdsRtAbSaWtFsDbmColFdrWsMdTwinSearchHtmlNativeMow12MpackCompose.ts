/**
 * Floating draft-before-full-merge residual over collective multiselect floating
 * DR workstation MD twin-search HTML-native mow12 pack (pure). Short moniker.
 *
 * Operator vision: provisional combined draft before full parent merge, while
 * collective cohesive unit + floating DR + workstation records + model decision
 * honesty remain pure — without draft write, parent merge, or live dispatch.
 *
 * draft_written / merge_executed always false.
 * live_dispatched / pack_dispatched / analysis_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  type ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
  type ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackInput,
} from "./colFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export interface DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackInput {
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  collective_pack: Omit<ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  collective_pack: ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  analysis_written: false;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  twin_written: false;
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
  inventory_mutated: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_market_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Draft-before-full-merge stacked on collective floating DR tip residual.
 * Never writes draft or merges parent; ND REJECT.
 */
export function composeDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack(
  input: DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackInput,
): DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.draft_gate || typeof input.draft_gate !== "object") {
    throw new Error("draft_gate must be an object");
  }
  if (!input.collective_pack || typeof input.collective_pack !== "object") {
    throw new Error("collective_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · merge_executed=false · live_dispatched=false",
    "pack_dispatched=false · analysis_written=false · record_persisted=false",
    "prompts_injected=false · production_router_verdict=REJECT",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const collective_pack = composeColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack({
    ...input.collective_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...collective_pack.notes.map((n) => `[collective_pack] ${n}`));

  const week_id = requireNonEmpty(collective_pack.week_id, "week_id");
  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(collective_pack.asset_id, "asset_id");
  const title = requireNonEmpty(collective_pack.title, "title");
  const account_id = requireNonEmpty(collective_pack.account_id, "account_id");

  const session_aligned = collective_pack.session_id === session_id;
  const parent_aligned =
    collective_pack.parent_asset_id === parent_asset_id ||
    collective_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      `session_aligned=false — draft_gate.session_id=${session_id} collective_pack.session_id=${collective_pack.session_id}`,
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      `parent_aligned=false — draft_gate.parent=${parent_asset_id} collective_pack.parent=${collective_pack.parent_asset_id} asset=${collective_pack.asset_id}`,
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      draft_gate.gate_ready === true &&
      collective_pack.pack_ready === true &&
      draft_gate.draft_written === false &&
      draft_gate.merge_executed === false &&
      draft_gate.live_dispatched === false &&
      collective_pack.live_dispatched === false &&
      collective_pack.pack_dispatched === false &&
      collective_pack.merge_executed === false &&
      collective_pack.analysis_written === false &&
      collective_pack.record_persisted === false &&
      collective_pack.prompts_injected === false &&
      collective_pack.live_router_authorized === false &&
      collective_pack.secrets_stored === false &&
      collective_pack.remote_index_queried === false &&
      collective_pack.twin_written === false &&
      collective_pack.purchase_executed === false &&
      collective_pack.hosted === false &&
      collective_pack.pdf_primary === false &&
      collective_pack.live_execution_authorized === false &&
      collective_pack.charge_executed === false &&
      collective_pack.draft_written === false &&
      collective_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned === true &&
      parent_aligned === true &&
      input.operator_ack === true &&
      draft_gate.draft_written === false &&
      draft_gate.merge_executed === false &&
      collective_pack.live_dispatched === false &&
      collective_pack.pack_dispatched === false &&
      collective_pack.record_persisted === false &&
      collective_pack.production_router_verdict === "REJECT" &&
      collective_pack.live_router_authorized === false &&
      (draft_gate.gate_ready === true || collective_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + collective floating DR tip residual ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — draft_gate, collective_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    draft_gate.draft_written !== false ||
    draft_gate.merge_executed !== false ||
    draft_gate.live_dispatched !== false ||
    collective_pack.live_dispatched !== false ||
    collective_pack.pack_dispatched !== false ||
    collective_pack.merge_executed !== false ||
    collective_pack.analysis_written !== false ||
    collective_pack.record_persisted !== false ||
    collective_pack.prompts_injected !== false ||
    collective_pack.live_router_authorized !== false ||
    collective_pack.secrets_stored !== false ||
    collective_pack.remote_index_queried !== false ||
    collective_pack.twin_written !== false ||
    collective_pack.purchase_executed !== false ||
    collective_pack.hosted !== false ||
    collective_pack.pdf_primary !== false ||
    collective_pack.live_execution_authorized !== false ||
    collective_pack.charge_executed !== false ||
    collective_pack.draft_written !== false ||
    collective_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("analysis_written=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
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
  notes.push("inventory_mutated=false");
  notes.push("production_router_verdict=REJECT");

  return {
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    title,
    account_id,
    draft_gate,
    collective_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    analysis_written: false,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    twin_written: false,
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
    inventory_mutated: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_market_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpack_compose_advisory",
  };
}

export function formatDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(
  c: DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `gate_ready=${c.draft_gate.gate_ready} · ` +
    `collective_ready=${c.collective_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · live_dispatched=false`
  );
}
