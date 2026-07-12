/**
 * Floating fullscreen-open residual over collective multiselect + floating DR
 * + draft-before-merge + MO price-ceiling pack (pure).
 *
 * Operator vision: open a floating deep-research instance fullscreen while
 * multi-select cohesive unit + floating DR + draft-before-merge + Midnight Oil
 * price-ceiling honesty remain pure — never live-dispatches research or MO.
 *
 * live_dispatched / pack_dispatched / merge_executed always false.
 * live_execution_authorized / charge_executed / analysis_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeCollectiveMultiselectFloatingDrDraftBeforeMerge,
  type CollectiveMultiselectFloatingDrDraftBeforeMergeCompose,
  type CollectiveMultiselectFloatingDrDraftBeforeMergeInput,
} from "./collectiveMultiselectFloatingDrDraftBeforeMergeCompose";

export interface FullscreenOpenCollectiveMultiselectFloatingDrInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  collective_pack: Omit<
    CollectiveMultiselectFloatingDrDraftBeforeMergeInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FullscreenOpenCollectiveMultiselectFloatingDrCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  collective_pack: CollectiveMultiselectFloatingDrDraftBeforeMergeCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
  analysis_written: false;
  twin_written: false;
  prompts_injected: false;
  record_persisted: false;
  remote_index_queried: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  purchase_executed: false;
  hosted: false;
  store_mutated: false;
  backlog_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  notes: string[];
  authority: "fullscreen_open_collective_multiselect_floating_dr_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Fullscreen-open stacked on collective multiselect floating DR pack.
 * Never live-dispatches research or MO workers.
 */
export function composeFullscreenOpenCollectiveMultiselectFloatingDr(
  input: FullscreenOpenCollectiveMultiselectFloatingDrInput,
): FullscreenOpenCollectiveMultiselectFloatingDrCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.fullscreen || typeof input.fullscreen !== "object") {
    throw new Error("fullscreen must be an object");
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
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "live_execution_authorized=false · charge_executed=false · analysis_written=false",
    "production_router_verdict=REJECT",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const collective_pack = composeCollectiveMultiselectFloatingDrDraftBeforeMerge({
    ...input.collective_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...collective_pack.notes.map((n) => `[collective_pack] ${n}`));

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(collective_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(collective_pack.asset_id, "asset_id");
  const title = requireNonEmpty(collective_pack.title, "title");
  const account_id = requireNonEmpty(collective_pack.account_id, "account_id");

  const session_aligned = collective_pack.session_id === session_id;
  const parent_aligned =
    collective_pack.parent_asset_id === parent_asset_id ||
    collective_pack.asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between fullscreen and collective_pack — pack_ready blocked",
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between fullscreen and collective_pack — pack_ready blocked",
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      fullscreen.fullscreen_ready === true &&
      collective_pack.pack_ready === true &&
      collective_pack.production_router_verdict === "REJECT" &&
      fullscreen.live_dispatched === false &&
      fullscreen.merge_executed === false &&
      fullscreen.pack_dispatched === false &&
      collective_pack.live_dispatched === false &&
      collective_pack.pack_dispatched === false &&
      collective_pack.merge_executed === false &&
      collective_pack.analysis_written === false &&
      collective_pack.twin_written === false &&
      collective_pack.draft_written === false &&
      collective_pack.live_execution_authorized === false &&
      collective_pack.charge_executed === false &&
      collective_pack.remote_index_queried === false &&
      collective_pack.pdf_primary === false &&
      collective_pack.live_router_authorized === false &&
      collective_pack.secrets_stored === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      collective_pack.production_router_verdict === "REJECT" &&
      collective_pack.pdf_primary === false &&
      fullscreen.live_dispatched === false &&
      (fullscreen.fullscreen_ready === true ||
        collective_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen + collective multiselect floating DR ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — fullscreen, collective_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    fullscreen.live_dispatched !== false ||
    fullscreen.merge_executed !== false ||
    fullscreen.pack_dispatched !== false ||
    collective_pack.live_dispatched !== false ||
    collective_pack.pack_dispatched !== false ||
    collective_pack.merge_executed !== false ||
    collective_pack.analysis_written !== false ||
    collective_pack.twin_written !== false ||
    collective_pack.draft_written !== false ||
    collective_pack.live_execution_authorized !== false ||
    collective_pack.charge_executed !== false ||
    collective_pack.remote_index_queried !== false ||
    collective_pack.pdf_primary !== false ||
    collective_pack.live_router_authorized !== false ||
    collective_pack.secrets_stored !== false ||
    collective_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("record_persisted=false");
  notes.push("remote_index_queried=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("store_mutated=false");
  notes.push("backlog_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    fullscreen,
    collective_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
    analysis_written: false,
    twin_written: false,
    prompts_injected: false,
    record_persisted: false,
    remote_index_queried: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    purchase_executed: false,
    hosted: false,
    store_mutated: false,
    backlog_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    notes,
    authority:
      "fullscreen_open_collective_multiselect_floating_dr_compose_advisory",
  };
}

export function formatFullscreenOpenCollectiveMultiselectFloatingDrSummary(
  c: FullscreenOpenCollectiveMultiselectFloatingDrCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `collective_ready=${c.collective_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · charge_executed=false · live_execution_authorized=false`
  );
}
