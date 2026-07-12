/**
 * Floating multi-select collective cohesive residual over floating DR +
 * draft-before-merge + MO price-ceiling pack (pure).
 *
 * Operator vision: click multiple floating/sub-agent deep research instances
 * and engage them as one cohesive unit while floating DR from highlights,
 * draft-before-merge, and Midnight Oil price-ceiling honesty remain pure —
 * without live dispatch, pack dispatch, analysis writes, or parent merges.
 *
 * live_dispatched / pack_dispatched / merge_executed / analysis_written always false.
 * twin_written / draft_written / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectCollectiveCohesiveInput,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composeFloatingDrDraftBeforeMergeMoPriceCeiling,
  type FloatingDrDraftBeforeMergeMoPriceCeilingCompose,
  type FloatingDrDraftBeforeMergeMoPriceCeilingInput,
} from "./floatingDrDraftBeforeMergeMoPriceCeilingCompose";

export interface CollectiveMultiselectFloatingDrDraftBeforeMergeInput {
  multiselect: Omit<FloatingMultiSelectCollectiveCohesiveInput, "operator_ack">;
  floating_dr_pack: Omit<
    FloatingDrDraftBeforeMergeMoPriceCeilingInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface CollectiveMultiselectFloatingDrDraftBeforeMergeCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  multiselect: FloatingMultiSelectCollectiveCohesiveCompose;
  floating_dr_pack: FloatingDrDraftBeforeMergeMoPriceCeilingCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  twin_written: false;
  draft_written: false;
  live_execution_authorized: false;
  charge_executed: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "collective_multiselect_floating_dr_draft_before_merge_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Multi-select collective cohesive stacked on floating DR draft-before-merge MO pack.
 * Never dispatches packs; never writes analysis; ND REJECT.
 */
export function composeCollectiveMultiselectFloatingDrDraftBeforeMerge(
  input: CollectiveMultiselectFloatingDrDraftBeforeMergeInput,
): CollectiveMultiselectFloatingDrDraftBeforeMergeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.multiselect || typeof input.multiselect !== "object") {
    throw new Error("multiselect must be an object");
  }
  if (!input.floating_dr_pack || typeof input.floating_dr_pack !== "object") {
    throw new Error("floating_dr_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "analysis_written=false · twin_written=false · draft_written=false",
    "production_router_verdict=REJECT",
  ];

  const multiselect = composeFloatingMultiSelectCollectiveCohesive({
    ...input.multiselect,
    operator_ack: input.operator_ack,
  });
  notes.push(...multiselect.notes.map((n) => `[multiselect] ${n}`));

  const floating_dr_pack = composeFloatingDrDraftBeforeMergeMoPriceCeiling({
    ...input.floating_dr_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...floating_dr_pack.notes.map((n) => `[floating_dr_pack] ${n}`));

  const session_id = requireNonEmpty(multiselect.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    multiselect.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(floating_dr_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(floating_dr_pack.asset_id, "asset_id");
  const title = requireNonEmpty(floating_dr_pack.title, "title");
  const account_id = requireNonEmpty(floating_dr_pack.account_id, "account_id");

  const session_aligned = floating_dr_pack.session_id === session_id;
  const parent_aligned =
    floating_dr_pack.parent_asset_id === parent_asset_id ||
    floating_dr_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between multiselect and floating_dr_pack — pack_ready blocked",
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between multiselect and floating_dr_pack — pack_ready blocked",
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      multiselect.pack_ready === true &&
      floating_dr_pack.pack_ready === true &&
      floating_dr_pack.production_router_verdict === "REJECT" &&
      multiselect.live_dispatched === false &&
      multiselect.pack_dispatched === false &&
      multiselect.merge_executed === false &&
      multiselect.analysis_written === false &&
      floating_dr_pack.live_dispatched === false &&
      floating_dr_pack.merge_executed === false &&
      floating_dr_pack.twin_written === false &&
      floating_dr_pack.draft_written === false &&
      floating_dr_pack.live_execution_authorized === false &&
      floating_dr_pack.charge_executed === false &&
      floating_dr_pack.remote_index_queried === false &&
      floating_dr_pack.pdf_primary === false &&
      floating_dr_pack.live_router_authorized === false &&
      floating_dr_pack.secrets_stored === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      floating_dr_pack.production_router_verdict === "REJECT" &&
      floating_dr_pack.pdf_primary === false &&
      multiselect.live_dispatched === false &&
      (multiselect.pack_ready === true || floating_dr_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — collective multiselect + floating DR draft-before-merge ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multiselect, floating_dr_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    multiselect.live_dispatched !== false ||
    multiselect.pack_dispatched !== false ||
    multiselect.merge_executed !== false ||
    multiselect.analysis_written !== false ||
    floating_dr_pack.live_dispatched !== false ||
    floating_dr_pack.merge_executed !== false ||
    floating_dr_pack.twin_written !== false ||
    floating_dr_pack.draft_written !== false ||
    floating_dr_pack.live_execution_authorized !== false ||
    floating_dr_pack.charge_executed !== false ||
    floating_dr_pack.remote_index_queried !== false ||
    floating_dr_pack.pdf_primary !== false ||
    floating_dr_pack.live_router_authorized !== false ||
    floating_dr_pack.secrets_stored !== false ||
    floating_dr_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("twin_written=false");
  notes.push("draft_written=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    multiselect,
    floating_dr_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    twin_written: false,
    draft_written: false,
    live_execution_authorized: false,
    charge_executed: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "collective_multiselect_floating_dr_draft_before_merge_compose_advisory",
  };
}

export function formatCollectiveMultiselectFloatingDrDraftBeforeMergeSummary(
  c: CollectiveMultiselectFloatingDrDraftBeforeMergeCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multi_ready=${c.multiselect.pack_ready} · ` +
    `float_ready=${c.floating_dr_pack.pack_ready} · ` +
    `mode=${c.multiselect.pack_mode} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · pack_dispatched=false · analysis_written=false`
  );
}
