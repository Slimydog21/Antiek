/**
 * Floating fullscreen-open residual over draft-before-merge floating
 * multi-select model decision pack (pure).
 *
 * Operator vision: open a floating deep-research instance fullscreen while
 * provisional draft-before-merge + multi-select cohesive unit + model decision
 * budget + twin search free settings remain pure.
 *
 * live_dispatched / merge_executed / draft_written always false.
 * live_router_authorized / secrets_stored / remote_index_queried always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeDraftBeforeMergeFloatingMultiselectModelDecision,
  type DraftBeforeMergeFloatingMultiselectModelDecisionCompose,
  type DraftBeforeMergeFloatingMultiselectModelDecisionInput,
} from "./draftBeforeMergeFloatingMultiselectModelDecisionCompose";

export interface FullscreenDraftBeforeMergeFloatingMultiselectInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  draft_pack: Omit<
    DraftBeforeMergeFloatingMultiselectModelDecisionInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FullscreenDraftBeforeMergeFloatingMultiselectCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  draft_pack: DraftBeforeMergeFloatingMultiselectModelDecisionCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
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
  authority: "fullscreen_draft_before_merge_floating_multiselect_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Fullscreen-open stacked on draft-before-merge floating multi-select pack.
 * Never live-dispatches; never merges; ND REJECT.
 */
export function composeFullscreenDraftBeforeMergeFloatingMultiselect(
  input: FullscreenDraftBeforeMergeFloatingMultiselectInput,
): FullscreenDraftBeforeMergeFloatingMultiselectCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.fullscreen || typeof input.fullscreen !== "object") {
    throw new Error("fullscreen must be an object");
  }
  if (!input.draft_pack || typeof input.draft_pack !== "object") {
    throw new Error("draft_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · merge_executed=false · draft_written=false",
    "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const draft_pack = composeDraftBeforeMergeFloatingMultiselectModelDecision({
    ...input.draft_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_pack.notes.map((n) => `[draft_pack] ${n}`));

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(draft_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(draft_pack.asset_id, "asset_id");
  const title = requireNonEmpty(draft_pack.title, "title");
  const account_id = requireNonEmpty(draft_pack.account_id, "account_id");

  const session_aligned = draft_pack.session_id === session_id;
  const parent_aligned =
    draft_pack.parent_asset_id === parent_asset_id ||
    draft_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between fullscreen and draft_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between fullscreen and draft_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      fullscreen.fullscreen_ready === true &&
      draft_pack.pack_ready === true &&
      fullscreen.live_dispatched === false &&
      fullscreen.merge_executed === false &&
      fullscreen.pack_dispatched === false &&
      draft_pack.draft_written === false &&
      draft_pack.merge_executed === false &&
      draft_pack.live_dispatched === false &&
      draft_pack.live_router_authorized === false &&
      draft_pack.secrets_stored === false &&
      draft_pack.remote_index_queried === false &&
      draft_pack.pdf_primary === false &&
      draft_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      fullscreen.merge_executed === false &&
      draft_pack.production_router_verdict === "REJECT" &&
      draft_pack.pdf_primary === false &&
      (fullscreen.fullscreen_ready === true || draft_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen + draft-before-merge multi-select model decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — fullscreen, draft_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    fullscreen.live_dispatched !== false ||
    fullscreen.merge_executed !== false ||
    fullscreen.pack_dispatched !== false ||
    draft_pack.draft_written !== false ||
    draft_pack.merge_executed !== false ||
    draft_pack.live_dispatched !== false ||
    draft_pack.live_router_authorized !== false ||
    draft_pack.secrets_stored !== false ||
    draft_pack.remote_index_queried !== false ||
    draft_pack.pdf_primary !== false ||
    draft_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
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
    fullscreen,
    draft_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
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
      "fullscreen_draft_before_merge_floating_multiselect_compose_advisory",
  };
}

export function formatFullscreenDraftBeforeMergeFloatingMultiselectSummary(
  c: FullscreenDraftBeforeMergeFloatingMultiselectCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `draft_pack_ready=${c.draft_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · merge_executed=false · draft_written=false`
  );
}
