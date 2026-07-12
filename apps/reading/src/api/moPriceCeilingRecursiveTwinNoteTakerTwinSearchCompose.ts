/**
 * Midnight Oil price-ceiling residual over recursive twin note-taker + twin
 * intelligent search + model decision HTML-native settings pack (pure).
 *
 * Operator vision: set time of work and goals; system recommends a price
 * ceiling to approve; package for unattended swarm while recursive twin
 * note-taker + twin search + model decision budget honesty remain pure —
 * never live-executes MO, charges, or writes twins.
 *
 * live_execution_authorized / charge_executed always false.
 * twin_written / prompts_injected / remote_index_queried always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMidnightOilPriceCeilingApproval,
  type MidnightOilPriceCeilingApprovalCompose,
  type MidnightOilPriceCeilingApprovalInput,
} from "./midnightOilPriceCeilingApprovalCompose";
import {
  composeRecursiveTwinNoteTakerTwinSearchModelDecision,
  type RecursiveTwinNoteTakerTwinSearchModelDecisionCompose,
  type RecursiveTwinNoteTakerTwinSearchModelDecisionInput,
} from "./recursiveTwinNoteTakerTwinSearchModelDecisionCompose";

export interface MoPriceCeilingRecursiveTwinNoteTakerTwinSearchInput {
  mo: Omit<MidnightOilPriceCeilingApprovalInput, "operator_ack">;
  twin_pack: Omit<
    RecursiveTwinNoteTakerTwinSearchModelDecisionInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require mo.pack_ready AND twin_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  mo: MidnightOilPriceCeilingApprovalCompose;
  twin_pack: RecursiveTwinNoteTakerTwinSearchModelDecisionCompose;
  pack_ready: boolean;
  live_execution_authorized: false;
  charge_executed: false;
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
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * MO price-ceiling approval stacked on recursive twin note-taker twin search pack.
 * Never launches MO workers; never charges; ND REJECT.
 */
export function composeMoPriceCeilingRecursiveTwinNoteTakerTwinSearch(
  input: MoPriceCeilingRecursiveTwinNoteTakerTwinSearchInput,
): MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.mo || typeof input.mo !== "object") {
    throw new Error("mo must be an object");
  }
  if (!input.twin_pack || typeof input.twin_pack !== "object") {
    throw new Error("twin_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false — MO never launches from pure pack",
    "charge_executed=false — recommended ceiling is advisory only",
    "twin_written=false · remote_index_queried=false · production_router_verdict=REJECT",
  ];

  const mo = composeMidnightOilPriceCeilingApproval({
    ...input.mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo.notes.map((n) => `[mo] ${n}`));

  const twin_pack = composeRecursiveTwinNoteTakerTwinSearchModelDecision({
    ...input.twin_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin_pack.notes.map((n) => `[twin_pack] ${n}`));

  const session_id = requireNonEmpty(twin_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    twin_pack.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(twin_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(twin_pack.asset_id, "asset_id");
  const title = requireNonEmpty(twin_pack.title, "title");
  const account_id = requireNonEmpty(twin_pack.account_id, "account_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo.pack_ready === true &&
      twin_pack.pack_ready === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      twin_pack.twin_written === false &&
      twin_pack.prompts_injected === false &&
      twin_pack.live_dispatch_authorized === false &&
      twin_pack.remote_index_queried === false &&
      twin_pack.pdf_primary === false &&
      twin_pack.pdf_view_authorized === false &&
      twin_pack.purchase_executed === false &&
      twin_pack.hosted === false &&
      twin_pack.secrets_stored === false &&
      twin_pack.live_router_authorized === false &&
      twin_pack.live_meter_read === false &&
      twin_pack.inventory_mutated === false &&
      twin_pack.suite_rewritten === false &&
      twin_pack.charge_executed === false &&
      twin_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      mo.live_execution_authorized === false &&
      mo.charge_executed === false &&
      twin_pack.twin_written === false &&
      twin_pack.remote_index_queried === false &&
      twin_pack.pdf_primary === false &&
      twin_pack.production_router_verdict === "REJECT" &&
      (mo.pack_ready === true || twin_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO price-ceiling + recursive twin note-taker twin search ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo, twin_pack, or operator_ack gate open",
    );
  }

  if (
    mo.live_execution_authorized !== false ||
    mo.charge_executed !== false ||
    twin_pack.twin_written !== false ||
    twin_pack.prompts_injected !== false ||
    twin_pack.live_dispatch_authorized !== false ||
    twin_pack.remote_index_queried !== false ||
    twin_pack.pdf_primary !== false ||
    twin_pack.pdf_view_authorized !== false ||
    twin_pack.purchase_executed !== false ||
    twin_pack.hosted !== false ||
    twin_pack.secrets_stored !== false ||
    twin_pack.live_router_authorized !== false ||
    twin_pack.live_meter_read !== false ||
    twin_pack.inventory_mutated !== false ||
    twin_pack.suite_rewritten !== false ||
    twin_pack.charge_executed !== false ||
    twin_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
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
    mo,
    twin_pack,
    pack_ready,
    live_execution_authorized: false,
    charge_executed: false,
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
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory",
  };
}

export function formatMoPriceCeilingRecursiveTwinNoteTakerTwinSearchSummary(
  c: MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose,
): string {
  const rec = c.mo.recommend.recommended_ceiling_usd;
  const recStr = rec === null ? "rec=null" : `rec=$${rec}`;
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo.pack_ready} · ` +
    `ceiling_approved=${c.mo.ceiling_approved} · ` +
    `${recStr} · ` +
    `twin_ready=${c.twin_pack.pack_ready} · ` +
    `stage=${c.mo.stage} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_execution_authorized=false · charge_executed=false · twin_written=false`
  );
}
