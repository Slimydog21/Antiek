/**
 * Competition DR quality over settings add-model + Antiek-bench source-attach MO (pure).
 *
 * Operator vision: world-class deep research quality/competition awareness
 * stacked on BYOK model inventory + Antiek-bench task→model rec + arxiv/
 * substack source attach + settings decision + Midnight Oil unattended pack.
 * Competition residuals remain advisory — never mutate backlog, never fetch,
 * never live-dispatch or auto-route.
 *
 * live_dispatch_authorized / remote_fetched / backlog_mutated always false.
 * secrets_stored / inventory_mutated / live_router_authorized always false.
 * suite_rewritten / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import {
  composeSettingsAddModelAntiekBenchSourceAttachMo,
  type SettingsAddModelAntiekBenchSourceAttachMoCompose,
  type SettingsAddModelAntiekBenchSourceAttachMoInput,
} from "./settingsAddModelAntiekBenchSourceAttachMoCompose";

export interface CompetitionDrSettingsAddModelBenchSourceMoInput {
  competition: Omit<CompetitionDrQualitySourcePackInput, "operator_ack">;
  settings_pack: Omit<
    SettingsAddModelAntiekBenchSourceAttachMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require competition.pack_ready AND settings_pack.pack_ready
   * and session_id alignment.
   */
  require_both?: boolean;
}

export interface CompetitionDrSettingsAddModelBenchSourceMoCompose {
  session_id: string;
  week_id: string;
  focus_task: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  asset_id: string;
  competition: CompetitionDrQualitySourcePackCompose;
  settings_pack: SettingsAddModelAntiekBenchSourceAttachMoCompose;
  /** Soft: session ids match across competition and settings pack. */
  session_aligned: boolean;
  pack_ready: boolean;
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
  pdf_view_authorized: false;
  pdf_primary: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  purchase_executed: false;
  hosted: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "competition_dr_settings_add_model_bench_source_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Competition DR quality stacked on settings add-model Antiek-bench source MO pack.
 * Never dispatches, fetches, mutates inventory/backlog, or live-routes.
 */
export function composeCompetitionDrSettingsAddModelBenchSourceMo(
  input: CompetitionDrSettingsAddModelBenchSourceMoInput,
): CompetitionDrSettingsAddModelBenchSourceMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.competition || typeof input.competition !== "object") {
    throw new Error("competition must be an object");
  }
  if (!input.settings_pack || typeof input.settings_pack !== "object") {
    throw new Error("settings_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false — competition DR pack is pure readiness",
    "remote_fetched=false — no arxiv/substack network fetch",
    "backlog_mutated=false — competition residuals advisory only",
    "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
    "suite_rewritten=false · production_router_verdict=REJECT",
  ];

  const competition = composeCompetitionDrQualitySourcePack({
    ...input.competition,
    operator_ack: input.operator_ack,
  });
  notes.push(...competition.notes.map((n) => `[competition] ${n}`));

  const settings_pack = composeSettingsAddModelAntiekBenchSourceAttachMo({
    ...input.settings_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings_pack.notes.map((n) => `[settings_pack] ${n}`));

  const session_id = requireNonEmpty(competition.session_id, "session_id");
  const week_id = requireNonEmpty(settings_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(settings_pack.focus_task, "focus_task");
  const parent_asset_id = requireNonEmpty(
    settings_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(settings_pack.title, "title");
  const account_id = requireNonEmpty(settings_pack.account_id, "account_id");
  const asset_id = requireNonEmpty(settings_pack.asset_id, "asset_id");

  const settings_session = requireNonEmpty(
    settings_pack.session_id,
    "settings_pack.session_id",
  );
  const session_aligned = session_id === settings_session;
  if (!session_aligned) {
    notes.push(
      `session_aligned=false — competition.session_id=${session_id} settings_pack.session_id=${settings_session}`,
    );
  } else {
    notes.push("session_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      competition.pack_ready === true &&
      settings_pack.pack_ready === true &&
      session_aligned === true &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      competition.backlog_mutated === false &&
      settings_pack.secrets_stored === false &&
      settings_pack.inventory_mutated === false &&
      settings_pack.live_router_authorized === false &&
      settings_pack.suite_rewritten === false &&
      settings_pack.remote_fetched === false &&
      settings_pack.live_execution_authorized === false &&
      settings_pack.purchase_executed === false &&
      settings_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      competition.live_dispatch_authorized === false &&
      competition.remote_fetched === false &&
      competition.backlog_mutated === false &&
      settings_pack.secrets_stored === false &&
      settings_pack.inventory_mutated === false &&
      settings_pack.live_router_authorized === false &&
      settings_pack.production_router_verdict === "REJECT" &&
      (competition.pack_ready === true || settings_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — competition DR + settings add-model bench source MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — competition, settings_pack, session align, or operator_ack gate open",
    );
  }

  if (
    competition.live_dispatch_authorized !== false ||
    competition.remote_fetched !== false ||
    competition.backlog_mutated !== false ||
    settings_pack.secrets_stored !== false ||
    settings_pack.inventory_mutated !== false ||
    settings_pack.live_router_authorized !== false ||
    settings_pack.suite_rewritten !== false ||
    settings_pack.store_mutated !== false ||
    settings_pack.remote_fetched !== false ||
    settings_pack.live_execution_authorized !== false ||
    settings_pack.purchase_executed !== false ||
    settings_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

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
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    week_id,
    focus_task,
    parent_asset_id,
    title,
    account_id,
    asset_id,
    competition,
    settings_pack,
    session_aligned,
    pack_ready,
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
    pdf_view_authorized: false,
    pdf_primary: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    purchase_executed: false,
    hosted: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "competition_dr_settings_add_model_bench_source_mo_compose_advisory",
  };
}

export function formatCompetitionDrSettingsAddModelBenchSourceMoSummary(
  c: CompetitionDrSettingsAddModelBenchSourceMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `comp_ready=${c.competition.pack_ready} · ` +
    `settings_ready=${c.settings_pack.pack_ready} · ` +
    `session_aligned=${c.session_aligned} · ` +
    `rec=${c.settings_pack.bench_pack.bench.recommendation?.recommended_model_id ?? "null"} · ` +
    `vs=${c.settings_pack.inventory_vs_bench} · ` +
    `week=${c.week_id} · task=${c.focus_task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false · inventory_mutated=false`
  );
}
