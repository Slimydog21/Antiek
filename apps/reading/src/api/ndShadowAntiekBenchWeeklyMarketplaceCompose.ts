/**
 * NotDiamond shadow REJECT + Antiek-bench weekly marketplace free source (pure).
 *
 * Operator vision: NotDiamond may advise model choice next to the decision tree,
 * but production routing is REJECT (§16). Overlay shadow advisory on weekly
 * bench learn + free-first marketplace research pack without live routing.
 *
 * production_router_verdict always REJECT; live_router_authorized always false.
 * backlog_mutated / store_mutated / purchase_executed / hosted always false.
 */

import {
  composeNotDiamondShadowAdvisory,
  type NotDiamondShadowAdvisoryCompose,
  type NotDiamondShadowAdvisoryInput,
} from "./notDiamondShadowAdvisoryCompose";
import {
  composeAntiekBenchWeeklyMarketplaceFreeSource,
  type AntiekBenchWeeklyMarketplaceFreeSourceCompose,
  type AntiekBenchWeeklyMarketplaceFreeSourceInput,
} from "./antiekBenchWeeklyMarketplaceFreeSourceCompose";

export interface NdShadowAntiekBenchWeeklyMarketplaceInput {
  nd_shadow: NotDiamondShadowAdvisoryInput;
  weekly_market: Omit<
    AntiekBenchWeeklyMarketplaceFreeSourceInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface NdShadowAntiekBenchWeeklyMarketplaceCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  nd_shadow: NotDiamondShadowAdvisoryCompose;
  weekly_market: AntiekBenchWeeklyMarketplaceFreeSourceCompose;
  pack_ready: boolean;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  backlog_mutated: false;
  store_mutated: false;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  prompts_injected: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  record_persisted: false;
  live_dispatch_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  notes: string[];
  authority: "nd_shadow_antiek_bench_weekly_marketplace_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * ND shadow advisory REJECT over weekly bench + marketplace free source pack.
 * Never live-routes; never mutates bench; never purchases/hosts.
 */
export function composeNdShadowAntiekBenchWeeklyMarketplace(
  input: NdShadowAntiekBenchWeeklyMarketplaceInput,
): NdShadowAntiekBenchWeeklyMarketplaceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.nd_shadow || typeof input.nd_shadow !== "object") {
    throw new Error("nd_shadow must be an object");
  }
  if (!input.weekly_market || typeof input.weekly_market !== "object") {
    throw new Error("weekly_market must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "production_router_verdict=REJECT · live_router_authorized=false",
    "backlog_mutated=false · store_mutated=false",
    "purchase_executed=false · hosted=false · remote_fetched=false",
  ];

  const nd_shadow = composeNotDiamondShadowAdvisory(input.nd_shadow);
  notes.push(...nd_shadow.notes.map((n) => `[nd_shadow] ${n}`));

  const weekly_market = composeAntiekBenchWeeklyMarketplaceFreeSource({
    ...input.weekly_market,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_market.notes.map((n) => `[weekly_market] ${n}`));

  const week_id = requireNonEmpty(weekly_market.week_id, "week_id");
  const session_id = requireNonEmpty(weekly_market.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    weekly_market.parent_asset_id,
    "parent_asset_id",
  );

  // ND is always REJECT — pack_ready requires that invariant held
  let pack_ready = false;
  if (require_both) {
    pack_ready =
      nd_shadow.production_router_verdict === "REJECT" &&
      nd_shadow.live_router_authorized === false &&
      weekly_market.pack_ready === true &&
      weekly_market.production_router_verdict === "REJECT" &&
      weekly_market.backlog_mutated === false &&
      weekly_market.store_mutated === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      nd_shadow.production_router_verdict === "REJECT" &&
      nd_shadow.live_router_authorized === false &&
      weekly_market.production_router_verdict === "REJECT" &&
      (nd_shadow.shadow_visible === true || weekly_market.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — ND shadow REJECT + weekly marketplace free source ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — nd_shadow, weekly_market, or operator_ack gate open",
    );
  }

  if (
    nd_shadow.production_router_verdict !== "REJECT" ||
    nd_shadow.live_router_authorized !== false ||
    weekly_market.production_router_verdict !== "REJECT" ||
    weekly_market.live_router_authorized !== false ||
    weekly_market.backlog_mutated !== false ||
    weekly_market.store_mutated !== false ||
    weekly_market.purchase_executed !== false ||
    weekly_market.hosted !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("prompts_injected=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("record_persisted=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");

  return {
    week_id,
    session_id,
    parent_asset_id,
    nd_shadow,
    weekly_market,
    pack_ready,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    backlog_mutated: false,
    store_mutated: false,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    prompts_injected: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    record_persisted: false,
    live_dispatch_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    notes,
    authority: "nd_shadow_antiek_bench_weekly_marketplace_compose_advisory",
  };
}

export function formatNdShadowAntiekBenchWeeklyMarketplaceSummary(
  c: NdShadowAntiekBenchWeeklyMarketplaceCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `shadow_visible=${c.nd_shadow.shadow_visible} · ` +
    `weekly_market_ready=${c.weekly_market.pack_ready} · ` +
    `proposals=${c.weekly_market.weekly_learn.proposal_count} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · backlog_mutated=false · purchase_executed=false`
  );
}
