/**
 * Competition DR quality + source pack over marketplace free-before-buy +
 * Antiek-bench recommend + Midnight Oil unattended (pure).
 *
 * Operator vision: highest-quality deep research — competition gap awareness
 * + arxiv/substack citations + quality/budget gate — stacked on MO unattended + arxiv/substack attach + recursive rewrite honesty. Never live-dispatches; never purchases.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * purchase_executed / hosted always false.
 * production_router_verdict always REJECT.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeMoUnattendedSourceAttachAntiekBenchRewrite,
  type MoUnattendedSourceAttachAntiekBenchRewriteCompose,
  type MoUnattendedSourceAttachAntiekBenchRewriteInput,
} from "./moUnattendedSourceAttachAntiekBenchRewriteCompose";

export interface CompetitionDrMoUnattendedSourceAttachRewriteInput {
  competition: Omit<CompetitionDrQualitySourcePackInput, "operator_ack">;
  mo_pack: Omit<MoUnattendedSourceAttachAntiekBenchRewriteInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require competition.pack_ready AND mo_pack.pack_ready
   * and session alignment.
   */
  require_both?: boolean;
}

export interface CompetitionDrMoUnattendedSourceAttachRewriteCompose {
  session_id: string;
  title: string;
  account_id: string;
  week_id: string;
  parent_asset_id: string;
  asset_id: string;
  competition: CompetitionDrQualitySourcePackCompose;
  mo_pack: MoUnattendedSourceAttachAntiekBenchRewriteCompose;
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
  authority: "competition_dr_mo_unattended_source_attach_rewrite_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Competition DR quality stacked on MO unattended source-attach rewrite.
 * Never live-dispatches; never purchases/hosts; ND REJECT.
 */
export function composeCompetitionDrMoUnattendedSourceAttachRewrite(
  input: CompetitionDrMoUnattendedSourceAttachRewriteInput,
): CompetitionDrMoUnattendedSourceAttachRewriteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  if (!input.mo_pack || typeof input.mo_pack !== "object") {
    throw new Error("mo_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
    "purchase_executed=false · hosted=false · pdf_primary=false",
    "production_router_verdict=REJECT",
  ];

  const competition = composeCompetitionDrQualitySourcePack({
    ...input.competition,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition.notes.map((n) => `[competition] ${n}`));

  const mo_pack = composeMoUnattendedSourceAttachAntiekBenchRewrite({
    ...input.mo_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...mo_pack.notes.map((n) => `[mo_pack] ${n}`));

  const session_id = requireNonEmpty(competition.session_id, "session_id");
  const title = requireNonEmpty(mo_pack.research_pack.title, "title");
  const account_id = requireNonEmpty(mo_pack.research_pack.account_id, "account_id");
  const week_id = requireNonEmpty(mo_pack.week_id, "week_id");
  const parent_asset_id = requireNonEmpty(
    mo_pack.parent_asset_id,
    "parent_asset_id",
  );
  const asset_id = requireNonEmpty(mo_pack.asset_id, "asset_id");

  const session_aligned = mo_pack.session_id === session_id;
  if (!session_aligned) {
    notes.push(
      "session_id mismatch between competition and mo_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      session_aligned &&
      competition.pack_ready === true &&
      mo_pack.pack_ready === true &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      competition.backlog_mutated === false &&
      mo_pack.purchase_executed === false &&
      mo_pack.hosted === false &&
      mo_pack.pdf_primary === false &&
      mo_pack.live_dispatch_authorized === false &&
      mo_pack.live_execution_authorized === false &&
      mo_pack.charge_executed === false &&
      mo_pack.suite_rewritten === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      session_aligned &&
      input.operator_ack === true &&
      competition.live_dispatch_authorized === false &&
      mo_pack.purchase_executed === false &&
      mo_pack.hosted === false &&
      mo_pack.production_router_verdict === "REJECT" &&
      mo_pack.pdf_primary === false &&
      (competition.pack_ready === true || mo_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition DR quality + MO unattended source-attach rewrite ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition, mo_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    competition.live_dispatch_authorized !== false ||
    competition.remote_fetched !== false ||
    competition.backlog_mutated !== false ||
    mo_pack.purchase_executed !== false ||
    mo_pack.hosted !== false ||
    mo_pack.pdf_primary !== false ||
    mo_pack.live_execution_authorized !== false ||
    mo_pack.charge_executed !== false ||
    mo_pack.suite_rewritten !== false ||
    mo_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false");
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
    title,
    account_id,
    week_id,
    parent_asset_id,
    asset_id,
    competition,
    mo_pack,
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
    authority: "competition_dr_mo_unattended_source_attach_rewrite_compose_advisory",
  };
}

export function formatCompetitionDrMoUnattendedSourceAttachRewriteSummary(
  c: CompetitionDrMoUnattendedSourceAttachRewriteCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `competition_ready=${c.competition.pack_ready} · ` +
    `mo_ready=${c.mo_pack.pack_ready} · ` +
    `ceiling_approved=${c.mo_pack.mo.ceiling_approved} · ` +
    `week=${c.week_id} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · charge_executed=false`
  );
}
