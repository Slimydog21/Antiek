/**
 * Competition DR quality residual over NotDiamond shadow REJECT + arxiv/substack
 * source-attach + Antiek-bench weekly learn + recursive twin presentation write
 * collective pack (pure).
 *
 * Operator vision: highest-quality deep research — competition gap awareness +
 * citation pack + quality/budget gate — stacked on ND shadow REJECT + source
 * attach + weekly learn + twin presentation honesty. Never live-dispatches;
 * never remote-fetches; ND production router REJECT held.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * live_router_authorized / twin_written / merge_executed always false.
 * production_router_verdict always REJECT.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeNdShadowSourceAttachWeeklyLearnTwinPresentation,
  type NdShadowSourceAttachWeeklyLearnTwinPresentationCompose,
  type NdShadowSourceAttachWeeklyLearnTwinPresentationInput,
} from "./ndShadowSourceAttachWeeklyLearnTwinPresentationCompose";

export interface CompetitionDrNdShadowSourceAttachWeeklyLearnInput {
  competition: Omit<CompetitionDrQualitySourcePackInput, "operator_ack">;
  nd_pack: Omit<
    NdShadowSourceAttachWeeklyLearnTwinPresentationInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface CompetitionDrNdShadowSourceAttachWeeklyLearnCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  asset_id: string;
  title: string;
  account_id: string;
  competition: CompetitionDrQualitySourcePackCompose;
  nd_pack: NdShadowSourceAttachWeeklyLearnTwinPresentationCompose;
  session_aligned: boolean;
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  twin_written: false;
  prompts_injected: false;
  merge_executed: false;
  draft_written: false;
  analysis_written: false;
  live_dispatched: false;
  pack_dispatched: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  remote_index_queried: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  inventory_mutated: false;
  charge_executed: false;
  record_persisted: false;
  purchase_executed: false;
  hosted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "competition_dr_nd_shadow_source_attach_weekly_learn_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Competition DR quality pack stacked on ND shadow source-attach weekly learn.
 * Never dispatches; never fetches; ND REJECT.
 */
export function composeCompetitionDrNdShadowSourceAttachWeeklyLearn(
  input: CompetitionDrNdShadowSourceAttachWeeklyLearnInput,
): CompetitionDrNdShadowSourceAttachWeeklyLearnCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  if (!input.nd_pack || typeof input.nd_pack !== "object") {
    throw new Error("nd_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "live_router_authorized=false · twin_written=false · merge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const competition = composeCompetitionDrQualitySourcePack({
    ...input.competition,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition.notes.map((n) => `[competition] ${n}`));

  const nd_pack = composeNdShadowSourceAttachWeeklyLearnTwinPresentation({
    ...input.nd_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...nd_pack.notes.map((n) => `[nd_pack] ${n}`));

  const session_id = requireNonEmpty(competition.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    nd_pack.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(nd_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(nd_pack.asset_id, "asset_id");
  const title = requireNonEmpty(nd_pack.title, "title");
  const account_id = requireNonEmpty(nd_pack.account_id, "account_id");

  const session_aligned = nd_pack.session_id === session_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between competition and nd_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      competition.pack_ready === true &&
      nd_pack.pack_ready === true &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      competition.backlog_mutated === false &&
      nd_pack.live_router_authorized === false &&
      nd_pack.remote_fetched === false &&
      nd_pack.backlog_mutated === false &&
      nd_pack.suite_rewritten === false &&
      nd_pack.twin_written === false &&
      nd_pack.merge_executed === false &&
      nd_pack.draft_written === false &&
      nd_pack.live_dispatched === false &&
      nd_pack.secrets_stored === false &&
      nd_pack.remote_index_queried === false &&
      nd_pack.pdf_primary === false &&
      nd_pack.production_router_verdict === "REJECT" &&
      nd_pack.nd_shadow.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      input.operator_ack === true &&
      competition.remote_fetched === false &&
      nd_pack.production_router_verdict === "REJECT" &&
      nd_pack.pdf_primary === false &&
      (competition.pack_ready === true || nd_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition DR + ND shadow source-attach weekly learn ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition, nd_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    competition.live_dispatch_authorized !== false ||
    competition.remote_fetched !== false ||
    competition.backlog_mutated !== false ||
    nd_pack.live_router_authorized !== false ||
    nd_pack.remote_fetched !== false ||
    nd_pack.backlog_mutated !== false ||
    nd_pack.suite_rewritten !== false ||
    nd_pack.twin_written !== false ||
    nd_pack.merge_executed !== false ||
    nd_pack.draft_written !== false ||
    nd_pack.live_dispatched !== false ||
    nd_pack.secrets_stored !== false ||
    nd_pack.remote_index_queried !== false ||
    nd_pack.pdf_primary !== false ||
    nd_pack.production_router_verdict !== "REJECT" ||
    nd_pack.nd_shadow.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("remote_index_queried=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("inventory_mutated=false");
  notes.push("charge_executed=false");
  notes.push("record_persisted=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    week_id,
    asset_id,
    title,
    account_id,
    competition,
    nd_pack,
    session_aligned,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    twin_written: false,
    prompts_injected: false,
    merge_executed: false,
    draft_written: false,
    analysis_written: false,
    live_dispatched: false,
    pack_dispatched: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    remote_index_queried: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    inventory_mutated: false,
    charge_executed: false,
    record_persisted: false,
    purchase_executed: false,
    hosted: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "competition_dr_nd_shadow_source_attach_weekly_learn_compose_advisory",
  };
}

export function formatCompetitionDrNdShadowSourceAttachWeeklyLearnSummary(
  c: CompetitionDrNdShadowSourceAttachWeeklyLearnCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `competition_ready=${c.competition.pack_ready} · ` +
    `nd_ready=${c.nd_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · live_router_authorized=false`
  );
}
