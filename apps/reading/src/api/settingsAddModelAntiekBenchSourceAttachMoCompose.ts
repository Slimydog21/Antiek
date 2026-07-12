/**
 * Settings add-model inventory over Antiek-bench source-attach settings MO pack (pure).
 *
 * Operator vision: while the full research workstation pack is ready
 * (bench task→model rec + arxiv/substack attach + decision-tree budget +
 * Midnight Oil unattended + fullscreen draft collective + paid free-first +
 * ND shadow REJECT + twin presentation), the operator can propose BYOK model
 * inventory ids in settings — never store secrets, never mutate inventory,
 * never auto-route, never rewrite the bench suite.
 *
 * secrets_stored / inventory_mutated always false.
 * live_router_authorized always false.
 * suite_rewritten / backlog_mutated / store_mutated always false.
 * remote_fetched / live_execution_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type SettingsAddModelInventoryInput,
} from "./settingsAddModelInventoryCompose";
import {
  composeAntiekBenchSourceAttachSettingsMo,
  type AntiekBenchSourceAttachSettingsMoCompose,
  type AntiekBenchSourceAttachSettingsMoInput,
} from "./antiekBenchSourceAttachSettingsMoCompose";

export type { SettingsAddModelInventoryInput };

export interface SettingsAddModelAntiekBenchSourceAttachMoInput {
  settings: Omit<SettingsAddModelInventoryInput, "operator_ack">;
  bench_pack: Omit<AntiekBenchSourceAttachSettingsMoInput, "operator_ack">;
  operator_ack: boolean;
  /**
   * When true (default), require settings.pack_ready AND bench_pack.pack_ready.
   */
  require_both?: boolean;
}

export interface SettingsAddModelAntiekBenchSourceAttachMoCompose {
  week_id: string;
  focus_task: string;
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  asset_id: string;
  settings: SettingsAddModelInventoryCompose;
  bench_pack: AntiekBenchSourceAttachSettingsMoCompose;
  /** Soft compare: inventory selection vs bench recommendation (advisory only). */
  inventory_vs_bench: "agree" | "disagree" | "bench_none" | "no_selection";
  pack_ready: boolean;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  secrets_meter_read: false;
  live_meter_read: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  remote_index_queried: false;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
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
  authority: "settings_add_model_antiek_bench_source_attach_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Settings add-model inventory stacked on Antiek-bench source-attach settings MO pack.
 * Never stores secrets; never mutates inventory; never live-routes or rewrites suite.
 */
export function composeSettingsAddModelAntiekBenchSourceAttachMo(
  input: SettingsAddModelAntiekBenchSourceAttachMoInput,
): SettingsAddModelAntiekBenchSourceAttachMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.settings || typeof input.settings !== "object") {
    throw new Error("settings must be an object");
  }
  if (!input.bench_pack || typeof input.bench_pack !== "object") {
    throw new Error("bench_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "secrets_stored=false — model ids only; never raw API keys",
    "inventory_mutated=false — propose_add is intent only",
    "live_router_authorized=false — operator selects model",
    "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
    "remote_fetched=false · live_execution_authorized=false",
    "production_router_verdict=REJECT",
  ];

  const settings = composeSettingsAddModelInventory({
    ...input.settings,
    operator_ack: input.operator_ack,
  });
  notes.push(...settings.notes.map((n) => `[settings] ${n}`));

  const bench_pack = composeAntiekBenchSourceAttachSettingsMo({
    ...input.bench_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...bench_pack.notes.map((n) => `[bench_pack] ${n}`));

  const week_id = requireNonEmpty(bench_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(bench_pack.focus_task, "focus_task");
  const session_id = requireNonEmpty(bench_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    bench_pack.parent_asset_id,
    "parent_asset_id",
  );
  const title = requireNonEmpty(bench_pack.title, "title");
  const account_id = requireNonEmpty(bench_pack.account_id, "account_id");
  const asset_id = requireNonEmpty(bench_pack.asset_id, "asset_id");

  const selected =
    settings.decision_tree?.driver.decision.selected_model_id ??
    input.settings.selected_model_id ??
    null;
  const rec = bench_pack.bench.recommendation?.recommended_model_id ?? null;

  let inventory_vs_bench: SettingsAddModelAntiekBenchSourceAttachMoCompose["inventory_vs_bench"];
  if (rec == null) {
    inventory_vs_bench = "bench_none";
    notes.push("inventory_vs_bench=bench_none — insufficient usage for task rec");
  } else if (selected == null || !String(selected).trim()) {
    inventory_vs_bench = "no_selection";
    notes.push("inventory_vs_bench=no_selection — no operator model selected");
  } else if (String(selected).trim() === rec) {
    inventory_vs_bench = "agree";
    notes.push(
      "inventory_vs_bench=agree — selection matches bench rec (still advisory)",
    );
  } else {
    inventory_vs_bench = "disagree";
    notes.push(
      `inventory_vs_bench=disagree — selected=${String(selected).trim()} rec=${rec} (operator wins)`,
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings.pack_ready === true &&
      bench_pack.pack_ready === true &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      settings.live_router_authorized === false &&
      bench_pack.live_router_authorized === false &&
      bench_pack.suite_rewritten === false &&
      bench_pack.backlog_mutated === false &&
      bench_pack.store_mutated === false &&
      bench_pack.remote_fetched === false &&
      bench_pack.pdf_primary === false &&
      bench_pack.live_execution_authorized === false &&
      bench_pack.purchase_executed === false &&
      bench_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      settings.secrets_stored === false &&
      settings.inventory_mutated === false &&
      bench_pack.live_router_authorized === false &&
      bench_pack.remote_fetched === false &&
      bench_pack.production_router_verdict === "REJECT" &&
      (settings.pack_ready === true || bench_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — settings add-model + Antiek-bench source attach MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — settings, bench_pack, or operator_ack gate open",
    );
  }

  if (
    settings.secrets_stored !== false ||
    settings.inventory_mutated !== false ||
    settings.live_router_authorized !== false ||
    bench_pack.live_router_authorized !== false ||
    bench_pack.suite_rewritten !== false ||
    bench_pack.backlog_mutated !== false ||
    bench_pack.store_mutated !== false ||
    bench_pack.remote_fetched !== false ||
    bench_pack.pdf_primary !== false ||
    bench_pack.live_execution_authorized !== false ||
    bench_pack.purchase_executed !== false ||
    bench_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("remote_index_queried=false");
  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
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
    week_id,
    focus_task,
    session_id,
    parent_asset_id,
    title,
    account_id,
    asset_id,
    settings,
    bench_pack,
    inventory_vs_bench,
    pack_ready,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    secrets_meter_read: false,
    live_meter_read: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    remote_index_queried: false,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
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
      "settings_add_model_antiek_bench_source_attach_mo_compose_advisory",
  };
}

export function formatSettingsAddModelAntiekBenchSourceAttachMoSummary(
  c: SettingsAddModelAntiekBenchSourceAttachMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `action=${c.settings.action} · ` +
    `proposed_new=${c.settings.proposed_new_count} · ` +
    `bench_ready=${c.bench_pack.pack_ready} · ` +
    `rec=${c.bench_pack.bench.recommendation?.recommended_model_id ?? "null"} · ` +
    `vs=${c.inventory_vs_bench} · ` +
    `week=${c.week_id} · task=${c.focus_task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `secrets_stored=false · inventory_mutated=false · live_router_authorized=false · suite_rewritten=false`
  );
}
