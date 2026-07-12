/**
 * Floating fullscreen-open residual over Midnight Oil unattended + draft-before-merge
 * floating multi-select model decision ND twin pack (pure).
 *
 * Operator vision: open a floating deep-research instance fullscreen while
 * MO unattended time/goals/ceiling + draft-before-merge + multi-select + model
 * decision ND twin honesty remain pure — never live-dispatches research or MO.
 *
 * live_dispatched / pack_dispatched / merge_executed always false.
 * live_execution_authorized / draft_written always false.
 * live_router_authorized / secrets_stored / remote_index_queried always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwin,
  type MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose,
  type MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinInput,
} from "./moUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose";

export interface FullscreenMoUnattendedDraftMultiselectNdTwinInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  mo_pack: Omit<
    MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FullscreenMoUnattendedDraftMultiselectNdTwinCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  mo_pack: MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
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
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Fullscreen-open stacked on MO unattended draft multiselect ND twin pack.
 * Never live-dispatches research or MO workers.
 */
export function composeFullscreenMoUnattendedDraftMultiselectNdTwin(
  input: FullscreenMoUnattendedDraftMultiselectNdTwinInput,
): FullscreenMoUnattendedDraftMultiselectNdTwinCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.fullscreen || typeof input.fullscreen !== "object") {
    throw new Error("fullscreen must be an object");
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
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "live_execution_authorized=false · draft_written=false",
    "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
    "production_router_verdict=REJECT",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const mo_pack = composeMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwin({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
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
      "session_id mismatch between fullscreen and mo_pack — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between fullscreen and mo_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      fullscreen.fullscreen_ready === true &&
      mo_pack.pack_ready === true &&
      mo_pack.production_router_verdict === "REJECT" &&
      fullscreen.live_dispatched === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.live_dispatched === false &&
      mo_pack.merge_executed === false &&
      mo_pack.draft_written === false &&
      mo_pack.live_router_authorized === false &&
      mo_pack.secrets_stored === false &&
      mo_pack.remote_index_queried === false &&
      mo_pack.pdf_primary === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      mo_pack.production_router_verdict === "REJECT" &&
      mo_pack.pdf_primary === false &&
      (fullscreen.fullscreen_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen + MO unattended draft multiselect ND twin ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — fullscreen, mo_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    fullscreen.live_dispatched !== false ||
    fullscreen.merge_executed !== false ||
    fullscreen.pack_dispatched !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.live_dispatched !== false ||
    mo_pack.merge_executed !== false ||
    mo_pack.draft_written !== false ||
    mo_pack.live_router_authorized !== false ||
    mo_pack.secrets_stored !== false ||
    mo_pack.remote_index_queried !== false ||
    mo_pack.pdf_primary !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
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
    mo_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
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
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory",
  };
}

export function formatFullscreenMoUnattendedDraftMultiselectNdTwinSummary(
  c: FullscreenMoUnattendedDraftMultiselectNdTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · live_execution_authorized=false · draft_written=false`
  );
}
