/**
 * Competition DR quality residual over source-attach + Antiek-bench recommend
 * + MO unattended fullscreen draft multi-select pack (pure).
 *
 * Operator vision: highest-quality deep research — competition gap awareness +
 * arxiv/substack citations + quality/budget gate — stacked on HTML-native
 * source attach + weekly task→model recommendation + Midnight Oil unattended.
 * Never live-dispatches; never remote-fetches; ND REJECT.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * purchase_executed / hosted / pdf_primary always false.
 * production_router_verdict always REJECT.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeSourceAttachAntiekBenchRecommendMoUnattended,
  type SourceAttachAntiekBenchRecommendMoUnattendedCompose,
  type SourceAttachAntiekBenchRecommendMoUnattendedInput,
} from "./sourceAttachAntiekBenchRecommendMoUnattendedCompose";

export interface CompetitionDrSourceAttachAntiekBenchRecommendInput {
  competition: Omit<CompetitionDrQualitySourcePackInput, "operator_ack">;
  source_pack: Omit<
    SourceAttachAntiekBenchRecommendMoUnattendedInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require competition.pack_ready AND source_pack.pack_ready
   * and session alignment.
   */
  require_both?: boolean;
}

export interface CompetitionDrSourceAttachAntiekBenchRecommendCompose {
  session_id: string;
  parent_asset_id: string;
  asset_id: string;
  week_id: string;
  focus_task: string;
  title: string;
  account_id: string;
  operator_id: string;
  competition: CompetitionDrQualitySourcePackCompose;
  source_pack: SourceAttachAntiekBenchRecommendMoUnattendedCompose;
  session_aligned: boolean;
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "competition_dr_source_attach_antiek_bench_recommend_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Competition DR quality stacked on source-attach Antiek-bench recommend pack.
 * Never live-dispatches; never purchases/hosts; ND REJECT.
 */
export function composeCompetitionDrSourceAttachAntiekBenchRecommend(
  input: CompetitionDrSourceAttachAntiekBenchRecommendInput,
): CompetitionDrSourceAttachAntiekBenchRecommendCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  if (!input.source_pack || typeof input.source_pack !== "object") {
    throw new Error("source_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "purchase_executed=false · hosted=false · pdf_primary=false",
    "suite_rewritten=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const competition = composeCompetitionDrQualitySourcePack({
    ...input.competition,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition.notes.map((n) => `[competition] ${n}`));

  const source_pack = composeSourceAttachAntiekBenchRecommendMoUnattended({
    ...input.source_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...source_pack.notes.map((n) => `[source_pack] ${n}`));

  const session_id = requireNonEmpty(competition.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    source_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(source_pack.asset_id, "asset_id");
  const week_id = requireNonEmpty(source_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(source_pack.focus_task, "focus_task");
  const title = requireNonEmpty(source_pack.title, "title");
  const account_id = requireNonEmpty(source_pack.account_id, "account_id");
  const operator_id = requireNonEmpty(source_pack.operator_id, "operator_id");

  const session_aligned = source_pack.session_id === session_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between competition and source_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      competition.pack_ready === true &&
      source_pack.pack_ready === true &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      competition.backlog_mutated === false &&
      source_pack.remote_fetched === false &&
      source_pack.purchase_executed === false &&
      source_pack.hosted === false &&
      source_pack.pdf_primary === false &&
      source_pack.live_dispatch_authorized === false &&
      source_pack.live_execution_authorized === false &&
      source_pack.charge_executed === false &&
      source_pack.suite_rewritten === false &&
      source_pack.live_router_authorized === false &&
      source_pack.secrets_stored === false &&
      source_pack.remote_index_queried === false &&
      source_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      input.operator_ack === true &&
      competition.live_dispatch_authorized === false &&
      source_pack.purchase_executed === false &&
      source_pack.hosted === false &&
      source_pack.production_router_verdict === "REJECT" &&
      source_pack.pdf_primary === false &&
      (competition.pack_ready === true || source_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition DR + source-attach Antiek-bench recommend ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition, source_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    competition.live_dispatch_authorized !== false ||
    competition.remote_fetched !== false ||
    competition.backlog_mutated !== false ||
    source_pack.remote_fetched !== false ||
    source_pack.purchase_executed !== false ||
    source_pack.hosted !== false ||
    source_pack.pdf_primary !== false ||
    source_pack.live_execution_authorized !== false ||
    source_pack.charge_executed !== false ||
    source_pack.suite_rewritten !== false ||
    source_pack.live_router_authorized !== false ||
    source_pack.secrets_stored !== false ||
    source_pack.remote_index_queried !== false ||
    source_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    asset_id,
    week_id,
    focus_task,
    title,
    account_id,
    operator_id,
    competition,
    source_pack,
    session_aligned,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "competition_dr_source_attach_antiek_bench_recommend_compose_advisory",
  };
}

export function formatCompetitionDrSourceAttachAntiekBenchRecommendSummary(
  c: CompetitionDrSourceAttachAntiekBenchRecommendCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `competition_ready=${c.competition.pack_ready} · ` +
    `source_ready=${c.source_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `behind=${c.competition.competition.behind_count} · ` +
    `focus=${c.focus_task} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · suite_rewritten=false`
  );
}
