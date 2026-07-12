/**
 * Floating draft-before-full-merge gate over multi-select workstation record
 * write twin pack (pure).
 *
 * Operator vision: create a provisional combined draft from floating sources
 * before full parent merge, while multi-select cohesive unit + workstation
 * record→prompt + write twin highlight remain pure honesty.
 *
 * draft_written / merge_executed always false.
 * live_dispatched / pack_dispatched / prompts_injected always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeMultiSelectWorkstationRecordWriteTwin,
  type MultiSelectWorkstationRecordWriteTwinCompose,
  type MultiSelectWorkstationRecordWriteTwinInput,
} from "./multiSelectWorkstationRecordWriteTwinCompose";

export interface DraftBeforeMergeMultiSelectRecordWriteInput {
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  multi_pack: Omit<
    MultiSelectWorkstationRecordWriteTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface DraftBeforeMergeMultiSelectRecordWriteCompose {
  session_id: string;
  parent_asset_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  multi_pack: MultiSelectWorkstationRecordWriteTwinCompose;
  pack_ready: boolean;
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
  authority: "draft_before_merge_multi_select_record_write_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Draft-before-full-merge stacked on multi-select record write twin pack.
 * Never writes draft or merges parent.
 */
export function composeDraftBeforeMergeMultiSelectRecordWrite(
  input: DraftBeforeMergeMultiSelectRecordWriteInput,
): DraftBeforeMergeMultiSelectRecordWriteCompose {
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
    "pack_dispatched=false · prompts_injected=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const multi_pack = composeMultiSelectWorkstationRecordWriteTwin({
    ...input.multi_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...multi_pack.notes.map((n) => `[multi_pack] ${n}`));

  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = multi_pack.session_id === session_id;
  const parent_aligned = multi_pack.parent_asset_id === parent_asset_id;
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
      multi_pack.prompts_injected === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      multi_pack.production_router_verdict === "REJECT" &&
      (draft_gate.gate_ready === true || multi_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + multi-select record write pack ready; still pure",
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
    multi_pack.prompts_injected !== false ||
    multi_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

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
    draft_gate,
    multi_pack,
    pack_ready,
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
    authority: "draft_before_merge_multi_select_record_write_compose_advisory",
  };
}

export function formatDraftBeforeMergeMultiSelectRecordWriteSummary(
  c: DraftBeforeMergeMultiSelectRecordWriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `gate_ready=${c.draft_gate.gate_ready} · ` +
    `multi_ready=${c.multi_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · live_dispatched=false`
  );
}
