/**
 * Floating collective multi-select of presented twins over paid-purchase
 * free-first + ND shadow twin presentation pack (pure).
 *
 * Operator vision: click multiple twin-presentation / deep-research instances
 * and engage them as one cohesive unit (cohesive prompt + optional analysis
 * merge intent) — still never live-dispatches or writes merges.
 *
 * live_dispatched / pack_dispatched / merge_executed / analysis_written always false.
 * purchase_executed / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectCollectiveCohesiveInput,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composePaidPurchaseNdShadowTwinPresentation,
  type PaidPurchaseNdShadowTwinPresentationCompose,
  type PaidPurchaseNdShadowTwinPresentationInput,
} from "./paidPurchaseNdShadowTwinPresentationCompose";

export interface CollectivePresentedTwinsPaidNdInput {
  collective: Omit<FloatingMultiSelectCollectiveCohesiveInput, "operator_ack">;
  paid_nd: Omit<PaidPurchaseNdShadowTwinPresentationInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require collective.pack_ready AND paid_nd.pack_ready
   * and parent_asset_id / session alignment.
   */
  require_both?: boolean;
}

export interface CollectivePresentedTwinsPaidNdCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  collective: FloatingMultiSelectCollectiveCohesiveCompose;
  paid_nd: PaidPurchaseNdShadowTwinPresentationCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
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
  draft_written: false;
  record_persisted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "collective_presented_twins_paid_nd_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Collective multi-select of presented twins + paid-purchase ND pack.
 * Never dispatches/merges/purchases; ND REJECT.
 */
export function composeCollectivePresentedTwinsPaidNd(
  input: CollectivePresentedTwinsPaidNdInput,
): CollectivePresentedTwinsPaidNdCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.collective || typeof input.collective !== "object") {
    throw new Error("collective must be an object");
  }
  if (!input.paid_nd || typeof input.paid_nd !== "object") {
    throw new Error("paid_nd must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false · merge_executed=false · analysis_written=false",
    "purchase_executed=false · live_router_authorized=false · twin_written=false",
    "production_router_verdict=REJECT",
  ];

  const collective = composeFloatingMultiSelectCollectiveCohesive({
    ...input.collective,
    operator_ack: input.operator_ack,
  });
  notes.push(...collective.notes.map((n) => `[collective] ${n}`));

  const paid_nd = composePaidPurchaseNdShadowTwinPresentation({
    ...input.paid_nd,
    operator_ack: input.operator_ack,
  });
  notes.push(...paid_nd.notes.map((n) => `[paid_nd] ${n}`));

  const session_id = requireNonEmpty(collective.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    collective.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(paid_nd.title, "title");
  const account_id = requireNonEmpty(paid_nd.account_id, "account_id");
  const week_id = requireNonEmpty(paid_nd.week_id, "week_id");
  const asset_id = requireNonEmpty(paid_nd.asset_id, "asset_id");

  const session_aligned = paid_nd.session_id === session_id;
  const parent_aligned = paid_nd.parent_asset_id === parent_asset_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between collective and paid_nd — pack_ready blocked",
    );
  }
  if (!parent_aligned) {
    notes.push(
      "parent_asset_id mismatch between collective and paid_nd — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      collective.pack_ready === true &&
      paid_nd.pack_ready === true &&
      collective.live_dispatched === false &&
      collective.pack_dispatched === false &&
      collective.merge_executed === false &&
      collective.analysis_written === false &&
      paid_nd.purchase_executed === false &&
      paid_nd.charge_executed === false &&
      paid_nd.hosted === false &&
      paid_nd.live_router_authorized === false &&
      paid_nd.twin_written === false &&
      paid_nd.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      parent_aligned &&
      input.operator_ack === true &&
      collective.merge_executed === false &&
      paid_nd.purchase_executed === false &&
      paid_nd.production_router_verdict === "REJECT" &&
      (collective.pack_ready === true || paid_nd.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — collective presented twins + paid-purchase ND pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — collective, paid_nd, alignment, or operator_ack gate open",
    );
  }

  if (
    collective.live_dispatched !== false ||
    collective.pack_dispatched !== false ||
    collective.merge_executed !== false ||
    collective.analysis_written !== false ||
    paid_nd.purchase_executed !== false ||
    paid_nd.charge_executed !== false ||
    paid_nd.hosted !== false ||
    paid_nd.live_router_authorized !== false ||
    paid_nd.twin_written !== false ||
    paid_nd.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
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
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    collective,
    paid_nd,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
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
    draft_written: false,
    record_persisted: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "collective_presented_twins_paid_nd_compose_advisory",
  };
}

export function formatCollectivePresentedTwinsPaidNdSummary(
  c: CollectivePresentedTwinsPaidNdCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `collective_ready=${c.collective.pack_ready} · ` +
    `mode=${c.collective.pack_mode} · ` +
    `paid_nd_ready=${c.paid_nd.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatched=false · merge_executed=false · purchase_executed=false`
  );
}
