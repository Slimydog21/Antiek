/**
 * Floating fullscreen-open over draft-before-merge collective presented twins
 * pack (pure).
 *
 * Operator vision: after provisional combined draft + multi-select collective
 * of presented twins, open a floating deep-research instance fullscreen —
 * without live dispatch or parent merge.
 *
 * live_dispatched / merge_executed / draft_written always false.
 * purchase_executed / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeDraftBeforeMergeCollectivePresentedTwins,
  type DraftBeforeMergeCollectivePresentedTwinsCompose,
  type DraftBeforeMergeCollectivePresentedTwinsInput,
} from "./draftBeforeMergeCollectivePresentedTwinsCompose";

export interface FullscreenDraftCollectivePresentedTwinsInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  draft_collective: Omit<
    DraftBeforeMergeCollectivePresentedTwinsInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FullscreenDraftCollectivePresentedTwinsCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  draft_collective: DraftBeforeMergeCollectivePresentedTwinsCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
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
  live_execution_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  live_meter_read: false;
  store_mutated: false;
  suite_rewritten: false;
  remote_index_queried: false;
  inventory_mutated: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "fullscreen_draft_collective_presented_twins_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Fullscreen-open stacked on draft-before-merge collective pack.
 * Never live-dispatches; never merges; never purchases; ND REJECT.
 */
export function composeFullscreenDraftCollectivePresentedTwins(
  input: FullscreenDraftCollectivePresentedTwinsInput,
): FullscreenDraftCollectivePresentedTwinsCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.fullscreen || typeof input.fullscreen !== "object") {
    throw new Error("fullscreen must be an object");
  }
  if (!input.draft_collective || typeof input.draft_collective !== "object") {
    throw new Error("draft_collective must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · merge_executed=false · draft_written=false",
    "purchase_executed=false · live_router_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const draft_collective = composeDraftBeforeMergeCollectivePresentedTwins({
    ...input.draft_collective,
    operator_ack: input.operator_ack,
  });
  notes.push(
    ...draft_collective.notes.map((n) => `[draft_collective] ${n}`),
  );

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(draft_collective.title, "title");
  const account_id = requireNonEmpty(
    draft_collective.account_id,
    "account_id",
  );
  const week_id = requireNonEmpty(draft_collective.week_id, "week_id");
  const asset_id = requireNonEmpty(draft_collective.asset_id, "asset_id");

  const session_aligned = draft_collective.session_id === session_id;
  const parent_aligned = draft_collective.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between fullscreen and draft_collective — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between fullscreen and draft_collective — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      fullscreen.fullscreen_ready === true &&
      draft_collective.pack_ready === true &&
      fullscreen.live_dispatched === false &&
      fullscreen.merge_executed === false &&
      fullscreen.pack_dispatched === false &&
      draft_collective.draft_written === false &&
      draft_collective.merge_executed === false &&
      draft_collective.live_dispatched === false &&
      draft_collective.purchase_executed === false &&
      draft_collective.live_router_authorized === false &&
      draft_collective.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      fullscreen.merge_executed === false &&
      draft_collective.purchase_executed === false &&
      draft_collective.production_router_verdict === "REJECT" &&
      (fullscreen.fullscreen_ready === true ||
        draft_collective.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen + draft-before-merge collective pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — fullscreen, draft_collective, alignment, or operator_ack gate open",
    );
  }

  if (
    fullscreen.live_dispatched !== false ||
    fullscreen.merge_executed !== false ||
    fullscreen.pack_dispatched !== false ||
    draft_collective.draft_written !== false ||
    draft_collective.merge_executed !== false ||
    draft_collective.live_dispatched !== false ||
    draft_collective.purchase_executed !== false ||
    draft_collective.live_router_authorized !== false ||
    draft_collective.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
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
  notes.push("live_execution_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
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
    fullscreen,
    draft_collective,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
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
    live_execution_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    live_meter_read: false,
    store_mutated: false,
    suite_rewritten: false,
    remote_index_queried: false,
    inventory_mutated: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "fullscreen_draft_collective_presented_twins_compose_advisory",
  };
}

export function formatFullscreenDraftCollectivePresentedTwinsSummary(
  c: FullscreenDraftCollectivePresentedTwinsCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `draft_collective_ready=${c.draft_collective.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · merge_executed=false · draft_written=false`
  );
}
