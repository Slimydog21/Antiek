/**
 * Floating multi-select collective cohesive over workstation record→prompt +
 * write twin highlight pack (pure).
 *
 * Operator vision: select multiple floating/sub-agent DR instances as one
 * cohesive unit, while workstation records inject into model decision and write
 * twin collective analysis rides on highlight float twin-search competition —
 * without live dispatch, pack execution, or asset writes.
 *
 * live_dispatched / pack_dispatched / merge_executed always false.
 * prompts_injected / record_persisted / remote_index_queried always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectCollectiveCohesiveInput,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composeWorkstationRecordWriteTwinHighlight,
  type WorkstationRecordWriteTwinHighlightCompose,
  type WorkstationRecordWriteTwinHighlightInput,
} from "./workstationRecordWriteTwinHighlightCompose";

export interface MultiSelectWorkstationRecordWriteTwinInput {
  multiselect: Omit<
    FloatingMultiSelectCollectiveCohesiveInput,
    "operator_ack"
  >;
  record_write: Omit<
    WorkstationRecordWriteTwinHighlightInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MultiSelectWorkstationRecordWriteTwinCompose {
  session_id: string;
  parent_asset_id: string;
  multiselect: FloatingMultiSelectCollectiveCohesiveCompose;
  record_write: WorkstationRecordWriteTwinHighlightCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  prompts_injected: false;
  record_persisted: false;
  live_router_authorized: false;
  remote_index_queried: false;
  twin_written: false;
  draft_written: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  notes: string[];
  authority: "multi_select_workstation_record_write_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Multi-select cohesive pack stacked on workstation record write twin highlight.
 * Never live-dispatches or injects prompts.
 */
export function composeMultiSelectWorkstationRecordWriteTwin(
  input: MultiSelectWorkstationRecordWriteTwinInput,
): MultiSelectWorkstationRecordWriteTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.multiselect || typeof input.multiselect !== "object") {
    throw new Error("multiselect must be an object");
  }
  if (!input.record_write || typeof input.record_write !== "object") {
    throw new Error("record_write must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "prompts_injected=false · record_persisted=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const multiselect = composeFloatingMultiSelectCollectiveCohesive({
    ...input.multiselect,
    operator_ack: input.operator_ack,
  });
  notes.push(...multiselect.notes.map((n) => `[multiselect] ${n}`));

  const record_write = composeWorkstationRecordWriteTwinHighlight({
    ...input.record_write,
    operator_ack: input.operator_ack,
  });
  notes.push(...record_write.notes.map((n) => `[record_write] ${n}`));

  const session_id = requireNonEmpty(multiselect.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    multiselect.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = record_write.session_id === session_id;
  const parent_aligned = record_write.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between multiselect and record_write — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between multiselect and record_write — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      multiselect.pack_ready === true &&
      record_write.pack_ready === true &&
      record_write.production_router_verdict === "REJECT" &&
      multiselect.live_dispatched === false &&
      multiselect.pack_dispatched === false &&
      record_write.prompts_injected === false &&
      record_write.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      record_write.production_router_verdict === "REJECT" &&
      (multiselect.pack_ready === true || record_write.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select cohesive + workstation record write twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multiselect, record_write, alignment, or operator_ack gate open",
    );
  }

  if (
    multiselect.live_dispatched !== false ||
    multiselect.pack_dispatched !== false ||
    multiselect.merge_executed !== false ||
    record_write.prompts_injected !== false ||
    record_write.record_persisted !== false ||
    record_write.remote_index_queried !== false ||
    record_write.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("prompts_injected=false");
  notes.push("record_persisted=false");
  notes.push("live_router_authorized=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("draft_written=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    multiselect,
    record_write,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    prompts_injected: false,
    record_persisted: false,
    live_router_authorized: false,
    remote_index_queried: false,
    twin_written: false,
    draft_written: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    notes,
    authority: "multi_select_workstation_record_write_twin_compose_advisory",
  };
}

export function formatMultiSelectWorkstationRecordWriteTwinSummary(
  c: MultiSelectWorkstationRecordWriteTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multiselect_ready=${c.multiselect.pack_ready} · ` +
    `record_write_ready=${c.record_write.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · pack_dispatched=false · prompts_injected=false`
  );
}
