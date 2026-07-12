/**
 * Reading highlight floating deep-research residual over draft-before-merge +
 * MO price-ceiling + recursive twin note-taker pack (pure).
 *
 * Operator vision: from a reading highlight, spin floating deep research /
 * tray + twin feed, while draft-before-full-merge, Midnight Oil price ceiling,
 * and recursive twin honesty remain pure — never live-dispatches, merges
 * parent, launches MO, or writes twins.
 *
 * live_dispatched / merge_executed / pack_dispatched / twin_written always false.
 * live_execution_authorized / charge_executed / draft_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeReadingHighlightFloatTwinFeed,
  type ReadingHighlightFloatTwinFeedCompose,
  type ReadingHighlightFloatTwinFeedInput,
} from "./readingHighlightFloatTwinFeedCompose";
import {
  composeDraftBeforeMergeMoPriceCeilingRecursiveTwin,
  type DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose,
  type DraftBeforeMergeMoPriceCeilingRecursiveTwinInput,
} from "./draftBeforeMergeMoPriceCeilingRecursiveTwinCompose";

export interface FloatingDrDraftBeforeMergeMoPriceCeilingInput {
  highlight_surface: Omit<ReadingHighlightFloatTwinFeedInput, "operator_ack">;
  draft_pack: Omit<
    DraftBeforeMergeMoPriceCeilingRecursiveTwinInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require highlight_surface.pack_ready AND
   * draft_pack.pack_ready, plus session/parent alignment.
   */
  require_both?: boolean;
}

export interface FloatingDrDraftBeforeMergeMoPriceCeilingCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  highlight_surface: ReadingHighlightFloatTwinFeedCompose;
  draft_pack: DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose;
  session_aligned: boolean;
  parent_aligned: boolean;
  pack_ready: boolean;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  twin_written: false;
  record_persisted: false;
  draft_written: false;
  live_execution_authorized: false;
  charge_executed: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  analysis_written: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "floating_dr_draft_before_merge_mo_price_ceiling_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Highlight floating DR stacked on draft-before-merge MO price-ceiling recursive twin.
 * Never live-dispatches; never merges; ND REJECT.
 */
export function composeFloatingDrDraftBeforeMergeMoPriceCeiling(
  input: FloatingDrDraftBeforeMergeMoPriceCeilingInput,
): FloatingDrDraftBeforeMergeMoPriceCeilingCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.highlight_surface || typeof input.highlight_surface !== "object") {
    throw new Error("highlight_surface must be an object");
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
    "live_dispatched=false · merge_executed=false · pack_dispatched=false",
    "twin_written=false · draft_written=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const highlight_surface = composeReadingHighlightFloatTwinFeed({
    ...input.highlight_surface,
    operator_ack: input.operator_ack,
  });
  notes.push(...highlight_surface.notes.map((n) => `[highlight_surface] ${n}`));

  const draft_pack = composeDraftBeforeMergeMoPriceCeilingRecursiveTwin({
    ...input.draft_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...draft_pack.notes.map((n) => `[draft_pack] ${n}`));

  const session_id = requireNonEmpty(
    highlight_surface.session_id,
    "session_id",
  );
  const parent_asset_id = requireNonEmpty(
    input.highlight_surface.parent_asset_id,
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
      "session_id mismatch between highlight_surface and draft_pack — pack_ready blocked",
    );
  } else {
    notes.push("session_aligned=true");
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between highlight_surface and draft_pack — pack_ready blocked",
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      highlight_surface.pack_ready === true &&
      draft_pack.pack_ready === true &&
      draft_pack.production_router_verdict === "REJECT" &&
      highlight_surface.live_dispatched === false &&
      highlight_surface.merge_executed === false &&
      highlight_surface.pack_dispatched === false &&
      highlight_surface.twin_written === false &&
      draft_pack.draft_written === false &&
      draft_pack.merge_executed === false &&
      draft_pack.live_dispatched === false &&
      draft_pack.live_execution_authorized === false &&
      draft_pack.charge_executed === false &&
      draft_pack.twin_written === false &&
      draft_pack.remote_index_queried === false &&
      draft_pack.pdf_primary === false &&
      draft_pack.live_router_authorized === false &&
      draft_pack.secrets_stored === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      draft_pack.production_router_verdict === "REJECT" &&
      draft_pack.pdf_primary === false &&
      highlight_surface.live_dispatched === false &&
      (highlight_surface.pack_ready === true || draft_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — floating DR highlight + draft-before-merge MO price-ceiling ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — highlight_surface, draft_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    highlight_surface.live_dispatched !== false ||
    highlight_surface.merge_executed !== false ||
    highlight_surface.pack_dispatched !== false ||
    highlight_surface.twin_written !== false ||
    draft_pack.draft_written !== false ||
    draft_pack.merge_executed !== false ||
    draft_pack.live_dispatched !== false ||
    draft_pack.live_execution_authorized !== false ||
    draft_pack.charge_executed !== false ||
    draft_pack.twin_written !== false ||
    draft_pack.remote_index_queried !== false ||
    draft_pack.pdf_primary !== false ||
    draft_pack.live_router_authorized !== false ||
    draft_pack.secrets_stored !== false ||
    draft_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("draft_written=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("analysis_written=false");
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
    highlight_surface,
    draft_pack,
    session_aligned,
    parent_aligned,
    pack_ready,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    twin_written: false,
    record_persisted: false,
    draft_written: false,
    live_execution_authorized: false,
    charge_executed: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    analysis_written: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "floating_dr_draft_before_merge_mo_price_ceiling_compose_advisory",
  };
}

export function formatFloatingDrDraftBeforeMergeMoPriceCeilingSummary(
  c: FloatingDrDraftBeforeMergeMoPriceCeilingCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `highlight_ready=${c.highlight_surface.pack_ready} · ` +
    `draft_ready=${c.draft_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · twin_written=false · draft_written=false · ` +
    `live_execution_authorized=false`
  );
}
