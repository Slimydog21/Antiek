/**
 * Workstation record→prompt model decision over write twin + highlight float
 * twin-search pack (pure).
 *
 * Operator vision: workstation records/insights/questions inject into model
 * decision prompts with usage bar + projection, stacked on write twin collective
 * analysis over highlight float DR + twin intelligent search competition pack —
 * recursive prompt-context honesty without live injection.
 *
 * record_persisted / prompts_injected / live_router_authorized always false.
 * draft_written / analysis_written / remote_index_queried always false.
 * production_router_verdict always REJECT.
 */

import {
  composeWorkstationRecordPromptModelDecision,
  type WorkstationRecordPromptModelDecisionCompose,
  type WorkstationRecordPromptModelDecisionInput,
} from "./workstationRecordPromptModelDecisionCompose";
import {
  composeWriteTwinCollectiveHighlightFloatTwinSearch,
  type WriteTwinCollectiveHighlightFloatTwinSearchCompose,
  type WriteTwinCollectiveHighlightFloatTwinSearchInput,
} from "./writeTwinCollectiveHighlightFloatTwinSearchCompose";

export interface WorkstationRecordWriteTwinHighlightInput {
  record_prompt: Omit<
    WorkstationRecordPromptModelDecisionInput,
    "operator_ack"
  >;
  write_pack: Omit<
    WriteTwinCollectiveHighlightFloatTwinSearchInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface WorkstationRecordWriteTwinHighlightCompose {
  session_id: string;
  parent_asset_id: string;
  record_prompt: WorkstationRecordPromptModelDecisionCompose;
  write_pack: WriteTwinCollectiveHighlightFloatTwinSearchCompose;
  pack_ready: boolean;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  live_dispatched: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  pack_dispatched: false;
  notes: string[];
  authority: "workstation_record_write_twin_highlight_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Workstation record→prompt decision stacked on write twin + highlight float pack.
 * Never injects prompts or writes records.
 */
export function composeWorkstationRecordWriteTwinHighlight(
  input: WorkstationRecordWriteTwinHighlightInput,
): WorkstationRecordWriteTwinHighlightCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.record_prompt || typeof input.record_prompt !== "object") {
    throw new Error("record_prompt must be an object");
  }
  if (!input.write_pack || typeof input.write_pack !== "object") {
    throw new Error("write_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "record_persisted=false · prompts_injected=false · live_router_authorized=false",
    "draft_written=false · analysis_written=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const record_prompt = composeWorkstationRecordPromptModelDecision({
    ...input.record_prompt,
    operator_ack: input.operator_ack,
  });
  notes.push(...record_prompt.notes.map((n) => `[record_prompt] ${n}`));

  const write_pack = composeWriteTwinCollectiveHighlightFloatTwinSearch({
    ...input.write_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...write_pack.notes.map((n) => `[write_pack] ${n}`));

  const session_id = requireNonEmpty(record_prompt.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    record_prompt.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = write_pack.session_id === session_id;
  const parent_aligned = write_pack.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between record_prompt and write_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between record_prompt and write_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      record_prompt.pack_ready === true &&
      write_pack.pack_ready === true &&
      write_pack.production_router_verdict === "REJECT" &&
      record_prompt.prompts_injected === false &&
      record_prompt.record_persisted === false &&
      write_pack.remote_index_queried === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      write_pack.production_router_verdict === "REJECT" &&
      (record_prompt.pack_ready === true || write_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — workstation record→prompt + write twin highlight pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — record_prompt, write_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    record_prompt.record_persisted !== false ||
    record_prompt.prompts_injected !== false ||
    record_prompt.live_router_authorized !== false ||
    write_pack.draft_written !== false ||
    write_pack.analysis_written !== false ||
    write_pack.remote_index_queried !== false ||
    write_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("live_dispatched=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    parent_asset_id,
    record_prompt,
    write_pack,
    pack_ready,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    live_dispatched: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    pack_dispatched: false,
    notes,
    authority: "workstation_record_write_twin_highlight_compose_advisory",
  };
}

export function formatWorkstationRecordWriteTwinHighlightSummary(
  c: WorkstationRecordWriteTwinHighlightCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `record_ready=${c.record_prompt.pack_ready} · ` +
    `write_ready=${c.write_pack.pack_ready} · ` +
    `usage=${c.record_prompt.usage_percent} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `prompts_injected=false · record_persisted=false · remote_index_queried=false`
  );
}
