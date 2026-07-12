/**
 * Draft-before-full-merge gate over collective presented twins + paid ND pack
 * (pure).
 *
 * Operator vision: after multi-select collective of presented twins, create a
 * provisional combined draft before fully merging into the parent asset.
 * Full merge still requires separate full_merge_ack — never executes.
 *
 * draft_written / merge_executed / live_dispatched always false.
 * purchase_executed / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingDraftBeforeFullMergeGate,
  type FloatingDraftBeforeFullMergeGateCompose,
  type FloatingDraftBeforeFullMergeGateInput,
} from "./floatingDraftBeforeFullMergeGateCompose";
import {
  composeCollectivePresentedTwinsPaidNd,
  type CollectivePresentedTwinsPaidNdCompose,
  type CollectivePresentedTwinsPaidNdInput,
} from "./collectivePresentedTwinsPaidNdCompose";

export interface DraftBeforeMergeCollectivePresentedTwinsInput {
  draft_gate: Omit<FloatingDraftBeforeFullMergeGateInput, "operator_ack">;
  collective_pack: Omit<CollectivePresentedTwinsPaidNdInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface DraftBeforeMergeCollectivePresentedTwinsCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  draft_gate: FloatingDraftBeforeFullMergeGateCompose;
  collective_pack: CollectivePresentedTwinsPaidNdCompose;
  pack_ready: boolean;
  draft_written: false;
  merge_executed: false;
  live_dispatched: false;
  pack_dispatched: false;
  analysis_written: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  live_meter_read: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  remote_index_queried: false;
  inventory_mutated: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "draft_before_merge_collective_presented_twins_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Draft-before-full-merge stacked on collective presented twins pack.
 * Never writes draft; never merges; never purchases; ND REJECT.
 */
export function composeDraftBeforeMergeCollectivePresentedTwins(
  input: DraftBeforeMergeCollectivePresentedTwinsInput,
): DraftBeforeMergeCollectivePresentedTwinsCompose {
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
    "purchase_executed=false · live_router_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const draft_gate = composeFloatingDraftBeforeFullMergeGate({
    ...input.draft_gate,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_gate.notes.map((n) => `[draft_gate] ${n}`));

  const collective_pack = composeCollectivePresentedTwinsPaidNd({
    ...input.collective_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(
    ...collective_pack.notes.map((n) => `[collective_pack] ${n}`),
  );

  const session_id = requireNonEmpty(draft_gate.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    draft_gate.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(collective_pack.title, "title");
  const account_id = requireNonEmpty(collective_pack.account_id, "account_id");
  const week_id = requireNonEmpty(collective_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(collective_pack.asset_id, "asset_id");

  const session_aligned = collective_pack.session_id === session_id;
  const parent_aligned = collective_pack.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between draft_gate and collective_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between draft_gate and collective_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      draft_gate.gate_ready === true &&
      collective_pack.pack_ready === true &&
      draft_gate.draft_written === false &&
      draft_gate.merge_executed === false &&
      draft_gate.live_dispatched === false &&
      collective_pack.live_dispatched === false &&
      collective_pack.merge_executed === false &&
      collective_pack.purchase_executed === false &&
      collective_pack.live_router_authorized === false &&
      collective_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      draft_gate.merge_executed === false &&
      collective_pack.purchase_executed === false &&
      collective_pack.production_router_verdict === "REJECT" &&
      (draft_gate.gate_ready === true || collective_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — draft-before-merge + collective presented twins ready; still pure",
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
    collective_pack.merge_executed !== false ||
    collective_pack.purchase_executed !== false ||
    collective_pack.live_router_authorized !== false ||
    collective_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("remote_index_queried=false");
  notes.push("inventory_mutated=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    draft_gate,
    collective_pack,
    pack_ready,
    draft_written: false,
    merge_executed: false,
    live_dispatched: false,
    pack_dispatched: false,
    analysis_written: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    live_meter_read: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    remote_index_queried: false,
    inventory_mutated: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "draft_before_merge_collective_presented_twins_compose_advisory",
  };
}

export function formatDraftBeforeMergeCollectivePresentedTwinsSummary(
  c: DraftBeforeMergeCollectivePresentedTwinsCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `gate_ready=${c.draft_gate.gate_ready} · ` +
    `stage=${c.draft_gate.stage} · ` +
    `collective_ready=${c.collective_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `draft_written=false · merge_executed=false · purchase_executed=false`
  );
}
