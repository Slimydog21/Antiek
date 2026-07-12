/**
 * Floating fullscreen-open over MO price-ceiling draft multi-select pack (pure).
 *
 * Operator vision: open a floating deep-research instance fullscreen while
 * midnight-oil price-ceiling approval and draft-before-merge multi-select
 * record write honesty remain pure — never live-dispatches research or MO.
 *
 * live_dispatched / pack_dispatched / merge_executed always false.
 * live_execution_authorized / charge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingFullscreenOpen,
  type FloatingFullscreenOpenCompose,
  type FloatingFullscreenOpenInput,
} from "./floatingFullscreenOpenCompose";
import {
  composeMoPriceCeilingDraftMultiSelectRecordWrite,
  type MoPriceCeilingDraftMultiSelectRecordWriteCompose,
  type MoPriceCeilingDraftMultiSelectRecordWriteInput,
} from "./moPriceCeilingDraftMultiSelectRecordWriteCompose";

export interface FullscreenMoPriceCeilingDraftMultiInput {
  fullscreen: Omit<FloatingFullscreenOpenInput, "operator_ack">;
  mo_pack: Omit<
    MoPriceCeilingDraftMultiSelectRecordWriteInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FullscreenMoPriceCeilingDraftMultiCompose {
  session_id: string;
  parent_asset_id: string;
  fullscreen: FloatingFullscreenOpenCompose;
  mo_pack: MoPriceCeilingDraftMultiSelectRecordWriteCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  live_execution_authorized: false;
  charge_executed: false;
  draft_written: false;
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
  authority: "fullscreen_mo_price_ceiling_draft_multi_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Fullscreen-open stacked on MO price-ceiling draft multi pack.
 * Never live-dispatches research or MO workers.
 */
export function composeFullscreenMoPriceCeilingDraftMulti(
  input: FullscreenMoPriceCeilingDraftMultiInput,
): FullscreenMoPriceCeilingDraftMultiCompose {
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
    "live_execution_authorized=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const fullscreen = composeFloatingFullscreenOpen({
    ...input.fullscreen,
    operator_ack: input.operator_ack,
  });
  notes.push(...fullscreen.notes.map((n) => `[fullscreen] ${n}`));

  const mo_pack = composeMoPriceCeilingDraftMultiSelectRecordWrite({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const session_id = requireNonEmpty(fullscreen.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    fullscreen.parent_asset_id,
    "parent_asset_id",
  );

  const session_aligned = mo_pack.session_id === session_id;
  const parent_aligned = mo_pack.parent_asset_id === parent_asset_id;
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
      mo_pack.charge_executed === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      mo_pack.production_router_verdict === "REJECT" &&
      (fullscreen.fullscreen_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — fullscreen + MO price-ceiling draft multi pack ready; still pure",
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
    mo_pack.charge_executed !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("draft_written=false");
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
    fullscreen,
    mo_pack,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    live_execution_authorized: false,
    charge_executed: false,
    draft_written: false,
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
    authority: "fullscreen_mo_price_ceiling_draft_multi_compose_advisory",
  };
}

export function formatFullscreenMoPriceCeilingDraftMultiSummary(
  c: FullscreenMoPriceCeilingDraftMultiCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `fullscreen_ready=${c.fullscreen.fullscreen_ready} · ` +
    `mo_pack_ready=${c.mo_pack.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · charge_executed=false · live_execution_authorized=false`
  );
}
