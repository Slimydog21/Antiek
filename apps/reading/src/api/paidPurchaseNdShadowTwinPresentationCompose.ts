/**
 * Marketplace paid-purchase free-first honesty over ND shadow twin
 * presentation + competition DR pack (pure).
 *
 * Operator vision: free HTML port first; paid path only when free unavailable
 * and price ceiling approved — still never charges. Stacks purchase honesty
 * on NotDiamond shadow REJECT + twin presentation pack.
 *
 * purchase_executed / charge_executed / hosted always false.
 * live_router_authorized / twin_written always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMarketplacePaidPurchaseGate,
  type MarketplacePaidPurchaseGateCompose,
  type MarketplacePaidPurchaseGateInput,
} from "./marketplacePaidPurchaseGateCompose";
import {
  composeNdShadowTwinPresentationCompetition,
  type NdShadowTwinPresentationCompetitionCompose,
  type NdShadowTwinPresentationCompetitionInput,
} from "./ndShadowTwinPresentationCompetitionCompose";

export interface PaidPurchaseNdShadowTwinPresentationInput {
  purchase: Omit<MarketplacePaidPurchaseGateInput, "operator_ack">;
  nd_twin: Omit<NdShadowTwinPresentationCompetitionInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require purchase.gate_ready AND nd_twin.pack_ready
   * (free-first gate must pass before twin/ND pack is considered ready together).
   */
  require_both?: boolean;
}

export interface PaidPurchaseNdShadowTwinPresentationCompose {
  title: string;
  account_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  week_id: string;
  purchase: MarketplacePaidPurchaseGateCompose;
  nd_twin: NdShadowTwinPresentationCompetitionCompose;
  pack_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
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
  live_dispatched: false;
  pack_dispatched: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "paid_purchase_nd_shadow_twin_presentation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Paid-purchase free-first honesty stacked on ND shadow twin presentation.
 * Never purchases/charges/hosts; ND REJECT.
 */
export function composePaidPurchaseNdShadowTwinPresentation(
  input: PaidPurchaseNdShadowTwinPresentationInput,
): PaidPurchaseNdShadowTwinPresentationCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.purchase || typeof input.purchase !== "object") {
    throw new Error("purchase must be an object");
  }
  if (!input.nd_twin || typeof input.nd_twin !== "object") {
    throw new Error("nd_twin must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "live_router_authorized=false · twin_written=false",
    "production_router_verdict=REJECT",
  ];

  const purchase = composeMarketplacePaidPurchaseGate({
    ...input.purchase,
    operator_ack: input.operator_ack,
  });
  notes.push(...purchase.notes.map((n) => `[purchase] ${n}`));

  const nd_twin = composeNdShadowTwinPresentationCompetition({
    ...input.nd_twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...nd_twin.notes.map((n) => `[nd_twin] ${n}`));

  const title = requireNonEmpty(purchase.free_port.title, "title");
  const account_id = requireNonEmpty(
    purchase.free_port.account_id,
    "account_id",
  );
  const session_id = requireNonEmpty(nd_twin.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    nd_twin.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(nd_twin.asset_id, "asset_id");
  const week_id = requireNonEmpty(nd_twin.week_id, "week_id");

  // Free-first honesty: if free available, purchase path must not pretend
  // purchase_ready without free preference (gate handles this internally).
  const free_first_honest =
    purchase.purchase_executed === false &&
    purchase.charge_executed === false &&
    purchase.hosted === false &&
    purchase.pdf_view_authorized === false;

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      free_first_honest &&
      purchase.gate_ready === true &&
      nd_twin.pack_ready === true &&
      nd_twin.live_router_authorized === false &&
      nd_twin.twin_written === false &&
      nd_twin.purchase_executed === false &&
      nd_twin.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      free_first_honest &&
      input.operator_ack === true &&
      purchase.purchase_executed === false &&
      nd_twin.production_router_verdict === "REJECT" &&
      (purchase.gate_ready === true || nd_twin.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — paid-purchase free-first + ND shadow twin presentation ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — purchase gate, nd_twin, free-first honesty, or operator_ack gate open",
    );
  }

  if (
    purchase.purchase_executed !== false ||
    purchase.charge_executed !== false ||
    purchase.hosted !== false ||
    nd_twin.live_router_authorized !== false ||
    nd_twin.twin_written !== false ||
    nd_twin.purchase_executed !== false ||
    nd_twin.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
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
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    title,
    account_id,
    session_id,
    parent_asset_id,
    asset_id,
    week_id,
    purchase,
    nd_twin,
    pack_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
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
    live_dispatched: false,
    pack_dispatched: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "paid_purchase_nd_shadow_twin_presentation_compose_advisory",
  };
}

export function formatPaidPurchaseNdShadowTwinPresentationSummary(
  c: PaidPurchaseNdShadowTwinPresentationCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `gate_ready=${c.purchase.gate_ready} · ` +
    `purchase_ready=${c.purchase.purchase_ready} · ` +
    `path=${c.purchase.free_port.path} · ` +
    `nd_twin_ready=${c.nd_twin.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `purchase_executed=false · charge_executed=false · live_router_authorized=false`
  );
}
