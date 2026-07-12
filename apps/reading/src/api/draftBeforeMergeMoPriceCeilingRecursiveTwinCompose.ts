/**
 * Floating draft-before-full-merge residual over MO price-ceiling + recursive
 * twin note-taker + twin intelligent search + model decision pack (pure).
 *
 * Operator vision: create a provisional combined draft from floating deep
 * research before fully merging into the parent asset, while Midnight Oil
 * price-ceiling approval and recursive twin honesty remain pure — never
 * writes draft, merges parent, launches MO, or live-routes.
 *
 * draft_written / merge_executed always false.
 * live_execution_authorized / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeMoPriceCeilingRecursiveTwinNoteTakerTwinSearch,
  type MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose,
  type MoPriceCeilingRecursiveTwinNoteTakerTwinSearchInput,
} from "./moPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose";

export interface DraftBeforeMergeMoPriceCeilingRecursiveTwinInput {
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  mo_pack: Omit<
    MoPriceCeilingRecursiveTwinNoteTakerTwinSearchInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  mo_pack: MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  analysis_written: false;
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
  live_execution_authorized: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "draft_before_merge_mo_price_ceiling_recursive_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Draft-before-merge gate stacked on MO price-ceiling recursive twin pack.
 * Never writes draft; never merges; never launches MO.
 */
export function composeDraftBeforeMergeMoPriceCeilingRecursiveTwin(
  input: DraftBeforeMergeMoPriceCeilingRecursiveTwinInput,
): DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.draft_gate || typeof input.draft_gate !== "object") {
    throw new Error("draft_gate must be an object");
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
    "draft_written=false · merge_executed=false · live_dispatched=false",
    "live_execution_authorized=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const mo_pack = composeMoPriceCeilingRecursiveTwinNoteTakerTwinSearch({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(mo_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(mo_pack.asset_id, "asset_id");
  const title = requireNonEmpty(mo_pack.title, "title");
  const account_id = requireNonEmpty(mo_pack.account_id, "account_id");

  const session_aligned = mo_pack.session_id === session_id;
  const parent_aligned =
    mo_pack.parent_asset_id === parent_asset_id ||
    mo_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between draft_gate and mo_pack — pack_ready blocked",
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between draft_gate and mo_pack — pack_ready blocked",
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      draft_gate.gate_ready === true &&
      mo_pack.pack_ready === true &&
      mo_pack.production_router_verdict === "REJECT" &&
      draft_gate.draft_written === false &&
      draft_gate.merge_executed === false &&
      draft_gate.live_dispatched === false &&
      mo_pack.live_dispatched === false &&
      mo_pack.pack_dispatched === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.charge_executed === false &&
      mo_pack.twin_written === false &&
      mo_pack.remote_index_queried === false &&
      mo_pack.pdf_primary === false &&
      mo_pack.live_router_authorized === false &&
      mo_pack.secrets_stored === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      mo_pack.production_router_verdict === "REJECT" &&
      mo_pack.pdf_primary === false &&
      mo_pack.live_execution_authorized === false &&
      (draft_gate.gate_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + MO price-ceiling recursive twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — draft_gate, mo_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    draft_gate.draft_written !== false ||
    draft_gate.merge_executed !== false ||
    draft_gate.live_dispatched !== false ||
    mo_pack.live_dispatched !== false ||
    mo_pack.pack_dispatched !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.charge_executed !== false ||
    mo_pack.twin_written !== false ||
    mo_pack.remote_index_queried !== false ||
    mo_pack.pdf_primary !== false ||
    mo_pack.live_router_authorized !== false ||
    mo_pack.secrets_stored !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("analysis_written=false");
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
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
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
    draft_gate,
    mo_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    analysis_written: false,
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
    live_execution_authorized: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "draft_before_merge_mo_price_ceiling_recursive_twin_compose_advisory",
  };
}

export function formatDraftBeforeMergeMoPriceCeilingRecursiveTwinSummary(
  c: DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `draft_gate_ready=${c.draft_gate.gate_ready} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · live_execution_authorized=false`
  );
}
