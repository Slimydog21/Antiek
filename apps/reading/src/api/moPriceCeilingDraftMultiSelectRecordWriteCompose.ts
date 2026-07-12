/**
 * Midnight Oil price-ceiling approval over draft-before-merge multi-select
 * record write pack (pure).
 *
 * Operator vision: unattended midnight-oil swarm with recommended price
 * ceiling approval, stacked on provisional draft-before-full-merge + multi-
 * select cohesive unit + workstation record write twin honesty — without live
 * execution or charges.
 *
 * live_execution_authorized / charge_executed always false.
 * draft_written / merge_executed / live_dispatched always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMidnightOilPriceCeilingApproval,
  type MidnightOilPriceCeilingApprovalCompose,
  type MidnightOilPriceCeilingApprovalInput,
} from "./midnightOilPriceCeilingApprovalCompose";
import {
  composeDraftBeforeMergeMultiSelectRecordWrite,
  type DraftBeforeMergeMultiSelectRecordWriteCompose,
  type DraftBeforeMergeMultiSelectRecordWriteInput,
} from "./draftBeforeMergeMultiSelectRecordWriteCompose";

export interface MoPriceCeilingDraftMultiSelectRecordWriteInput {
  mo: Omit<MidnightOilPriceCeilingApprovalInput, "operator_ack">;
  draft_multi: Omit<
    DraftBeforeMergeMultiSelectRecordWriteInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MoPriceCeilingDraftMultiSelectRecordWriteCompose {
  session_id: string;
  parent_asset_id: string;
  operator_id: string;
  mo: MidnightOilPriceCeilingApprovalCompose;
  draft_multi: DraftBeforeMergeMultiSelectRecordWriteCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  prompts_injected: false;
  record_persisted: false;
  remote_index_queried: false;
  twin_written: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  notes: string[];
  authority: "mo_price_ceiling_draft_multi_select_record_write_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO price-ceiling approval stacked on draft-before-merge multi-select pack.
 * Never authorizes live MO execution or charges.
 */
export function composeMoPriceCeilingDraftMultiSelectRecordWrite(
  input: MoPriceCeilingDraftMultiSelectRecordWriteInput,
): MoPriceCeilingDraftMultiSelectRecordWriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.draft_multi || typeof input.draft_multi !== "object") {
    throw new Error("draft_multi must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false · charge_executed=false",
    "draft_written=false · merge_executed=false · live_dispatched=false",
    "production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilPriceCeilingApproval({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const draft_multi = composeDraftBeforeMergeMultiSelectRecordWrite({
    ...input.draft_multi,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_multi.notes.map((n) => `[draft_multi] ${n}`));

  const session_id = requireNonEmpty(draft_multi.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_multi.parent_asset_id,
    "parent_asset_id",
  );
  const operator_id = requireNonEmpty(mo.operator_id, "operator_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.pack_ready === true &&
      draft_multi.pack_ready === true &&
      draft_multi.production_router_verdict === "REJECT" &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      draft_multi.draft_written === false &&
      draft_multi.merge_executed === false &&
      draft_multi.live_dispatched === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      draft_multi.production_router_verdict === "REJECT" &&
      mo.charge_executed === false &&
      (mo.pack_ready === true || draft_multi.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO price-ceiling + draft multi-select record write ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, draft_multi, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    mo.charge_executed !== false ||
    draft_multi.draft_written !== false ||
    draft_multi.merge_executed !== false ||
    draft_multi.live_dispatched !== false ||
    draft_multi.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("prompts_injected=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    operator_id,
    mo,
    draft_multi,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    prompts_injected: false,
    record_persisted: false,
    remote_index_queried: false,
    twin_written: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    notes,
    authority:
      "mo_price_ceiling_draft_multi_select_record_write_compose_advisory",
  };
}

export function formatMoPriceCeilingDraftMultiSelectRecordWriteSummary(
  c: MoPriceCeilingDraftMultiSelectRecordWriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.pack_ready} · ` +
    `ceiling_approved=${c.mo.ceiling_approved} · ` +
    `draft_multi_ready=${c.draft_multi.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · charge_executed=false · draft_written=false`
  );
}
