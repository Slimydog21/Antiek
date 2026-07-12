/**
 * Antiek-bench weekly usage-learn + marketplace free source-attach pack (pure).
 *
 * Operator vision: recursive Antiek-bench that learns from weekly usage to
 * rewrite sub-benchmarks — overlaid on free-first marketplace + arxiv/substack
 * research pack so model-quality feedback informs the full workstation without
 * mutating bench store or purchasing/hosting.
 *
 * backlog_mutated / store_mutated always false.
 * purchase_executed / hosted / remote_fetched always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeAntiekBenchWeeklyUsageLearn,
  type AntiekBenchWeeklyUsageLearnCompose,
  type AntiekBenchWeeklyUsageLearnInput,
} from "./antiekBenchWeeklyUsageLearnCompose";
import {
  composeMarketplaceFreeSourceAttachRecordPrompt,
  type MarketplaceFreeSourceAttachRecordPromptCompose,
  type MarketplaceFreeSourceAttachRecordPromptInput,
} from "./marketplaceFreeSourceAttachRecordPromptCompose";

export interface AntiekBenchWeeklyMarketplaceFreeSourceInput {
  weekly_learn: Omit<AntiekBenchWeeklyUsageLearnInput, "operator_ack">;
  market_research: Omit<
    MarketplaceFreeSourceAttachRecordPromptInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface AntiekBenchWeeklyMarketplaceFreeSourceCompose {
  week_id: string;
  session_id: string;
  parent_asset_id: string;
  weekly_learn: AntiekBenchWeeklyUsageLearnCompose;
  market_research: MarketplaceFreeSourceAttachRecordPromptCompose;
  pack_ready: boolean;
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
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  notes: string[];
  authority: "antiek_bench_weekly_marketplace_free_source_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Antiek-bench weekly learn overlay on marketplace free source-attach pack.
 * Never mutates bench store; never purchases/hosts; never remote-fetches.
 */
export function composeAntiekBenchWeeklyMarketplaceFreeSource(
  input: AntiekBenchWeeklyMarketplaceFreeSourceInput,
): AntiekBenchWeeklyMarketplaceFreeSourceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.weekly_learn || typeof input.weekly_learn !== "object") {
    throw new Error("weekly_learn must be an object");
  }
  if (!input.market_research || typeof input.market_research !== "object") {
    throw new Error("market_research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "backlog_mutated=false · store_mutated=false",
    "purchase_executed=false · hosted=false · remote_fetched=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const weekly_learn = composeAntiekBenchWeeklyUsageLearn({
    ...input.weekly_learn,
    operator_ack: input.operator_ack,
  });
  notes.push(...weekly_learn.notes.map((n) => `[weekly_learn] ${n}`));

  const market_research = composeMarketplaceFreeSourceAttachRecordPrompt({
    ...input.market_research,
    operator_ack: input.operator_ack,
  });
  notes.push(...market_research.notes.map((n) => `[market_research] ${n}`));

  const week_id = requireNonEmpty(weekly_learn.week_id, "week_id");
  const session_id = requireNonEmpty(market_research.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    market_research.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      weekly_learn.learn_ready === true &&
      market_research.pack_ready === true &&
      market_research.production_router_verdict === "REJECT" &&
      weekly_learn.backlog_mutated === false &&
      weekly_learn.store_mutated === false &&
      market_research.purchase_executed === false &&
      market_research.hosted === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      market_research.production_router_verdict === "REJECT" &&
      weekly_learn.store_mutated === false &&
      (weekly_learn.learn_ready === true || market_research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — weekly bench learn + marketplace free source pack ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — weekly_learn, market_research, or operator_ack gate open",
    );
  }

  if (
    weekly_learn.backlog_mutated !== false ||
    weekly_learn.store_mutated !== false ||
    market_research.purchase_executed !== false ||
    market_research.hosted !== false ||
    market_research.remote_fetched !== false ||
    market_research.production_router_verdict !== "REJECT" ||
    market_research.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

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
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");

  return {
    week_id,
    session_id,
    parent_asset_id,
    weekly_learn,
    market_research,
    pack_ready,
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
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    notes,
    authority: "antiek_bench_weekly_marketplace_free_source_compose_advisory",
  };
}

export function formatAntiekBenchWeeklyMarketplaceFreeSourceSummary(
  c: AntiekBenchWeeklyMarketplaceFreeSourceCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `learn_ready=${c.weekly_learn.learn_ready} · ` +
    `proposals=${c.weekly_learn.proposal_count} · ` +
    `market_research_ready=${c.market_research.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `backlog_mutated=false · store_mutated=false · purchase_executed=false`
  );
}
