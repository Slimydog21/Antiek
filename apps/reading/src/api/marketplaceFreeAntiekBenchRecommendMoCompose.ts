/**
 * Marketplace free-before-buy HTML port over Antiek-bench recommend +
 * Midnight Oil unattended pack (pure).
 *
 * Operator vision: pure reading — prefer free HTML copy, port into account
 * only when ready; never auto-purchase; while bench task→model rec + MO
 * unattended honesty remain pure.
 *
 * purchase_executed / hosted always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_router_authorized / live_execution_authorized / charge_executed false.
 * production_router_verdict always REJECT.
 */

import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
  type MarketplaceFreeBeforeBuyHtmlPortInput,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";
import {
  composeAntiekBenchRecommendMoUnattended,
  type AntiekBenchRecommendMoUnattendedCompose,
  type AntiekBenchRecommendMoUnattendedInput,
} from "./antiekBenchRecommendMoUnattendedCompose";

export interface MarketplaceFreeAntiekBenchRecommendMoInput {
  market: MarketplaceFreeBeforeBuyHtmlPortInput;
  bench_mo: Omit<AntiekBenchRecommendMoUnattendedInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require market.port_ready AND bench_mo.pack_ready.
   */
  require_both?: boolean;
}

export interface MarketplaceFreeAntiekBenchRecommendMoCompose {
  title: string;
  account_id: string;
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  market: MarketplaceFreeBeforeBuyHtmlPortCompose;
  bench_mo: AntiekBenchRecommendMoUnattendedCompose;
  pack_ready: boolean;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_fetched: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "marketplace_free_antiek_bench_recommend_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Free-before-buy HTML port stacked on Antiek-bench recommend + MO unattended.
 * Never purchases; never hosts; never PDF-primary; ND REJECT.
 */
export function composeMarketplaceFreeAntiekBenchRecommendMo(
  input: MarketplaceFreeAntiekBenchRecommendMoInput,
): MarketplaceFreeAntiekBenchRecommendMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.market || typeof input.market !== "object") {
    throw new Error("market must be an object");
  }
  if (!input.bench_mo || typeof input.bench_mo !== "object") {
    throw new Error("bench_mo must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · hosted=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "live_router_authorized=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const market = composeMarketplaceFreeBeforeBuyHtmlPort(input.market);
  notes.push(...market.notes.map((n) => `[market] ${n}`));

  const bench_mo = composeAntiekBenchRecommendMoUnattended({
    ...input.bench_mo,
    operator_ack: input.operator_ack,
  });
  notes.push(...bench_mo.notes.map((n) => `[bench_mo] ${n}`));

  const title = requireNonEmpty(market.title, "title");
  const account_id = requireNonEmpty(market.account_id, "account_id");
  const week_id = requireNonEmpty(bench_mo.week_id, "week_id");
  const session_id = requireNonEmpty(bench_mo.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    bench_mo.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(bench_mo.asset_id, "asset_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      market.port_ready === true &&
      bench_mo.pack_ready === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      market.pdf_view_authorized === false &&
      bench_mo.live_router_authorized === false &&
      bench_mo.suite_rewritten === false &&
      bench_mo.live_execution_authorized === false &&
      bench_mo.charge_executed === false &&
      bench_mo.purchase_executed === false &&
      bench_mo.hosted === false &&
      bench_mo.pdf_primary === false &&
      bench_mo.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      market.pdf_view_authorized === false &&
      bench_mo.production_router_verdict === "REJECT" &&
      bench_mo.pdf_primary === false &&
      (market.port_ready === true || bench_mo.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — free-before-buy port + Antiek-bench recommend MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market, bench_mo, or operator_ack gate open",
    );
  }

  if (
    market.purchase_executed !== false ||
    market.hosted !== false ||
    market.pdf_view_authorized !== false ||
    bench_mo.live_router_authorized !== false ||
    bench_mo.suite_rewritten !== false ||
    bench_mo.live_execution_authorized !== false ||
    bench_mo.charge_executed !== false ||
    bench_mo.purchase_executed !== false ||
    bench_mo.hosted !== false ||
    bench_mo.pdf_primary !== false ||
    bench_mo.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    title,
    account_id,
    week_id,
    session_id,
    parent_asset_id,
    asset_id,
    market,
    bench_mo,
    pack_ready,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_fetched: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority: "marketplace_free_antiek_bench_recommend_mo_compose_advisory",
  };
}

export function formatMarketplaceFreeAntiekBenchRecommendMoSummary(
  c: MarketplaceFreeAntiekBenchRecommendMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `port_ready=${c.market.port_ready} · ` +
    `path=${c.market.path} · ` +
    `bench_mo_ready=${c.bench_mo.pack_ready} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `purchase_executed=false · hosted=false · pdf_primary=false`
  );
}
