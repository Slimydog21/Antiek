/**
 * Marketplace free-before-buy over competition DR + settings add-model bench MO (pure).
 *
 * Operator vision: free-first digital book HTML port readiness stacked on
 * world-class competition DR quality + BYOK inventory + Antiek-bench +
 * source-attach + Midnight Oil pack. Prefer free HTML; never auto-purchase;
 * never host account bytes in this pure layer.
 *
 * purchase_executed / hosted always false.
 * pdf_view_authorized / pdf_primary always false.
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * secrets_stored / inventory_mutated / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
  type MarketplaceFreeBeforeBuyHtmlPortInput,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";
import {
  composeCompetitionDrSettingsAddModelBenchSourceMo,
  type CompetitionDrSettingsAddModelBenchSourceMoCompose,
  type CompetitionDrSettingsAddModelBenchSourceMoInput,
} from "./competitionDrSettingsAddModelBenchSourceMoCompose";

export interface MarketplaceFreeCompetitionDrSettingsBenchMoInput {
  market: MarketplaceFreeBeforeBuyHtmlPortInput;
  competition_pack: Omit<
    CompetitionDrSettingsAddModelBenchSourceMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require market.port_ready AND competition_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface MarketplaceFreeCompetitionDrSettingsBenchMoCompose {
  title: string;
  account_id: string;
  session_id: string;
  week_id: string;
  focus_task: string;
  parent_asset_id: string;
  asset_id: string;
  market: MarketplaceFreeBeforeBuyHtmlPortCompose;
  competition_pack: CompetitionDrSettingsAddModelBenchSourceMoCompose;
  pack_ready: boolean;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  suite_rewritten: false;
  store_mutated: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "marketplace_free_competition_dr_settings_bench_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Free-before-buy HTML port stacked on competition DR settings add-model pack.
 * Never purchases; never hosts; never PDF-primary; ND REJECT.
 */
export function composeMarketplaceFreeCompetitionDrSettingsBenchMo(
  input: MarketplaceFreeCompetitionDrSettingsBenchMoInput,
): MarketplaceFreeCompetitionDrSettingsBenchMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.market || typeof input.market !== "object") {
    throw new Error("market must be an object");
  }
  if (!input.competition_pack || typeof input.competition_pack !== "object") {
    throw new Error("competition_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · hosted=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const market = composeMarketplaceFreeBeforeBuyHtmlPort(input.market);
  notes.push(...market.notes.map((n) => `[market] ${n}`));

  const competition_pack = composeCompetitionDrSettingsAddModelBenchSourceMo({
    ...input.competition_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition_pack.notes.map((n) => `[competition_pack] ${n}`));

  const title = requireNonEmpty(market.title, "title");
  const account_id = requireNonEmpty(market.account_id, "account_id");
  const session_id = requireNonEmpty(competition_pack.session_id, "session_id");
  const week_id = requireNonEmpty(competition_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(competition_pack.focus_task, "focus_task");
  const parent_asset_id = requireNonEmpty(
    competition_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(competition_pack.asset_id, "asset_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      market.port_ready === true &&
      competition_pack.pack_ready === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      market.pdf_view_authorized === false &&
      competition_pack.live_dispatch_authorized === false &&
      competition_pack.remote_fetched === false &&
      competition_pack.backlog_mutated === false &&
      competition_pack.inventory_mutated === false &&
      competition_pack.secrets_stored === false &&
      competition_pack.live_router_authorized === false &&
      competition_pack.suite_rewritten === false &&
      competition_pack.live_execution_authorized === false &&
      competition_pack.purchase_executed === false &&
      competition_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      market.purchase_executed === false &&
      market.hosted === false &&
      competition_pack.live_dispatch_authorized === false &&
      competition_pack.remote_fetched === false &&
      competition_pack.production_router_verdict === "REJECT" &&
      (market.port_ready === true || competition_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — marketplace free + competition DR settings bench MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market, competition_pack, or operator_ack gate open",
    );
  }

  if (
    market.purchase_executed !== false ||
    market.hosted !== false ||
    market.pdf_view_authorized !== false ||
    competition_pack.live_dispatch_authorized !== false ||
    competition_pack.remote_fetched !== false ||
    competition_pack.backlog_mutated !== false ||
    competition_pack.inventory_mutated !== false ||
    competition_pack.secrets_stored !== false ||
    competition_pack.live_router_authorized !== false ||
    competition_pack.suite_rewritten !== false ||
    competition_pack.live_execution_authorized !== false ||
    competition_pack.purchase_executed !== false ||
    competition_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("suite_rewritten=false");
  notes.push("store_mutated=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
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
    session_id,
    week_id,
    focus_task,
    parent_asset_id,
    asset_id,
    market,
    competition_pack,
    pack_ready,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    suite_rewritten: false,
    store_mutated: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "marketplace_free_competition_dr_settings_bench_mo_compose_advisory",
  };
}

export function formatMarketplaceFreeCompetitionDrSettingsBenchMoSummary(
  c: MarketplaceFreeCompetitionDrSettingsBenchMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `market_path=${c.market.path} · port_ready=${c.market.port_ready} · ` +
    `comp_ready=${c.competition_pack.pack_ready} · ` +
    `session_aligned=${c.competition_pack.session_aligned} · ` +
    `week=${c.week_id} · task=${c.focus_task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `purchase_executed=false · hosted=false · live_dispatch_authorized=false · inventory_mutated=false`
  );
}
