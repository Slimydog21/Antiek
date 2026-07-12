/**
 * Competition DR quality source pack + ND shadow weekly marketplace (pure).
 *
 * Operator vision: highest-quality deep research product — competition gap
 * awareness + arxiv/substack citations + quality/budget gate, stacked on ND
 * shadow REJECT + Antiek-bench weekly + free marketplace pack. Never live-
 * dispatches, scrapes, or production-routes via NotDiamond.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 * purchase_executed / hosted / store_mutated always false.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeNdShadowAntiekBenchWeeklyMarketplace,
  type NdShadowAntiekBenchWeeklyMarketplaceCompose,
  type NdShadowAntiekBenchWeeklyMarketplaceInput,
} from "./ndShadowAntiekBenchWeeklyMarketplaceCompose";

export interface CompetitionDrNdShadowWeeklyMarketplaceInput {
  competition: Omit<CompetitionDrQualitySourcePackInput, "operator_ack">;
  nd_weekly: Omit<NdShadowAntiekBenchWeeklyMarketplaceInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface CompetitionDrNdShadowWeeklyMarketplaceCompose {
  session_id: string;
  week_id: string;
  parent_asset_id: string;
  competition: CompetitionDrQualitySourcePackCompose;
  nd_weekly: NdShadowAntiekBenchWeeklyMarketplaceCompose;
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  store_mutated: false;
  purchase_executed: false;
  hosted: false;
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
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  notes: string[];
  authority: "competition_dr_nd_shadow_weekly_marketplace_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Competition DR quality pack over ND shadow weekly marketplace stack.
 * Never live-dispatches; never scrapes; ND never production router.
 */
export function composeCompetitionDrNdShadowWeeklyMarketplace(
  input: CompetitionDrNdShadowWeeklyMarketplaceInput,
): CompetitionDrNdShadowWeeklyMarketplaceCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  if (!input.nd_weekly || typeof input.nd_weekly !== "object") {
    throw new Error("nd_weekly must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
    "purchase_executed=false · hosted=false · store_mutated=false",
  ];

  const competition = composeCompetitionDrQualitySourcePack({
    ...input.competition,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition.notes.map((n) => `[competition] ${n}`));

  const nd_weekly = composeNdShadowAntiekBenchWeeklyMarketplace({
    ...input.nd_weekly,
    operator_ack: input.operator_ack,
  });
  notes.push(...nd_weekly.notes.map((n) => `[nd_weekly] ${n}`));

  const session_id = requireNonEmpty(competition.session_id, "session_id");
  const week_id = requireNonEmpty(nd_weekly.week_id, "week_id");
  const parent_asset_id = requireNonEmpty(
    nd_weekly.parent_asset_id,
    "parent_asset_id",
  );

  const aligned = nd_weekly.session_id === session_id;
  if (!aligned) {
    notes.push(
      "session_id mismatch between competition and nd_weekly — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      competition.pack_ready === true &&
      nd_weekly.pack_ready === true &&
      nd_weekly.production_router_verdict === "REJECT" &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      nd_weekly.live_router_authorized === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      nd_weekly.production_router_verdict === "REJECT" &&
      competition.remote_fetched === false &&
      (competition.pack_ready === true || nd_weekly.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition DR quality + ND shadow weekly marketplace ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition, nd_weekly, alignment, or operator_ack gate open",
    );
  }

  if (
    competition.live_dispatch_authorized !== false ||
    competition.remote_fetched !== false ||
    competition.backlog_mutated !== false ||
    nd_weekly.production_router_verdict !== "REJECT" ||
    nd_weekly.live_router_authorized !== false ||
    nd_weekly.backlog_mutated !== false ||
    nd_weekly.store_mutated !== false ||
    nd_weekly.purchase_executed !== false ||
    nd_weekly.hosted !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("store_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
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
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");

  return {
    session_id,
    week_id,
    parent_asset_id,
    competition,
    nd_weekly,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    store_mutated: false,
    purchase_executed: false,
    hosted: false,
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
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    notes,
    authority: "competition_dr_nd_shadow_weekly_marketplace_compose_advisory",
  };
}

export function formatCompetitionDrNdShadowWeeklyMarketplaceSummary(
  c: CompetitionDrNdShadowWeeklyMarketplaceCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `competition_ready=${c.competition.pack_ready} · ` +
    `behind=${c.competition.competition.behind_count} · ` +
    `nd_weekly_ready=${c.nd_weekly.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · live_router_authorized=false`
  );
}
