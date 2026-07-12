/**
 * Floating draft-before-full-merge gate residual over floating multi-select
 * model decision twin search free settings pack (pure).
 *
 * Operator vision: provisional combined draft from floating sources before
 * full parent merge, while multi-select cohesive unit + model decision budget
 * + twin intelligent search HTML-native free marketplace remain pure.
 *
 * draft_written / merge_executed always false.
 * live_dispatched / pack_dispatched always false.
 * live_router_authorized / secrets_stored / live_meter_read always false.
 * remote_index_queried / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeFloatingMultiselectModelDecisionTwinSearchFreeSettings,
  type FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose,
  type FloatingMultiselectModelDecisionTwinSearchFreeSettingsInput,
} from "./floatingMultiselectModelDecisionTwinSearchFreeSettingsCompose";

export interface DraftBeforeMergeFloatingMultiselectModelDecisionInput {
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  multi_pack: Omit<
    FloatingMultiselectModelDecisionTwinSearchFreeSettingsInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface DraftBeforeMergeFloatingMultiselectModelDecisionCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  multi_pack: FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose;
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
  authority: "draft_before_merge_floating_multiselect_model_decision_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Draft-before-full-merge stacked on floating multi-select model decision pack.
 * Never writes draft or merges parent.
 */
export function composeDraftBeforeMergeFloatingMultiselectModelDecision(
  input: DraftBeforeMergeFloatingMultiselectModelDecisionInput,
): DraftBeforeMergeFloatingMultiselectModelDecisionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.draft_gate || typeof input.draft_gate !== "object") {
    throw new Error("draft_gate must be an object");
  }
  if (!input.multi_pack || typeof input.multi_pack !== "object") {
    throw new Error("multi_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "draft_written=false · merge_executed=false · live_dispatched=false",
    "pack_dispatched=false · live_router_authorized=false · secrets_stored=false",
    "remote_index_queried=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const multi_pack = composeFloatingMultiselectModelDecisionTwinSearchFreeSettings({
    ...input.multi_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...multi_pack.notes.map((n) => `[multi_pack] ${n}`));

  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(multi_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(multi_pack.asset_id, "asset_id");
  const title = requireNonEmpty(multi_pack.title, "title");
  const account_id = requireNonEmpty(multi_pack.account_id, "account_id");

  const session_aligned = multi_pack.session_id === session_id;
  const parent_aligned =
    multi_pack.parent_asset_id === parent_asset_id ||
    multi_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between draft_gate and multi_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between draft_gate and multi_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      draft_gate.gate_ready === true &&
      multi_pack.pack_ready === true &&
      multi_pack.production_router_verdict === "REJECT" &&
      draft_gate.draft_written === false &&
      draft_gate.merge_executed === false &&
      multi_pack.live_dispatched === false &&
      multi_pack.pack_dispatched === false &&
      multi_pack.live_router_authorized === false &&
      multi_pack.secrets_stored === false &&
      multi_pack.remote_index_queried === false &&
      multi_pack.pdf_primary === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      multi_pack.production_router_verdict === "REJECT" &&
      multi_pack.pdf_primary === false &&
      (draft_gate.gate_ready === true || multi_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + floating multi-select model decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — draft_gate, multi_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    draft_gate.draft_written !== false ||
    draft_gate.merge_executed !== false ||
    draft_gate.live_dispatched !== false ||
    multi_pack.live_dispatched !== false ||
    multi_pack.pack_dispatched !== false ||
    multi_pack.live_router_authorized !== false ||
    multi_pack.secrets_stored !== false ||
    multi_pack.remote_index_queried !== false ||
    multi_pack.pdf_primary !== false ||
    multi_pack.production_router_verdict !== "REJECT"
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
    multi_pack,
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
      "draft_before_merge_floating_multiselect_model_decision_compose_advisory",
  };
}

export function formatDraftBeforeMergeFloatingMultiselectModelDecisionSummary(
  c: DraftBeforeMergeFloatingMultiselectModelDecisionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `draft_gate_ready=${c.draft_gate.gate_ready} · ` +
    `multi_pack_ready=${c.multi_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · live_dispatched=false`
  );
}
