/**
 * Settings add-model inventory + Antiek-bench task model recommendation (pure).
 *
 * Operator vision: add models in settings (BYOK ids only), see Antiek-bench
 * task recommendations in the decision-tree tab with usage bar + prompt cost
 * projection — optimize model quality per task without auto-routing or
 * storing secrets.
 *
 * secrets_stored / inventory_mutated / live_router_authorized always false.
 * suite_rewritten / backlog_mutated / store_mutated always false.
 */

import {
  composeSettingsAddModelInventory,
  type SettingsAddModelInventoryCompose,
  type AddModelAction,
} from "./settingsAddModelInventoryCompose";
import type { InventoryModelRow } from "./settingsModelInventoryBudgetCompose";
import {
  composeAntiekBenchTaskModelRecommendation,
  type AntiekBenchTaskModelRecommendationCompose,
} from "./antiekBenchTaskModelRecommendationCompose";
import type { WeeklyUsageEvent } from "./antiekBenchWeeklyUsageLearnCompose";
import type { TaskFamilySeed } from "./antiekBenchTaskFamilyExpandCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";

export type { AddModelAction };

export interface SettingsAddModelBenchDecisionInput {
  /** Current inventory (ids only). */
  models: InventoryModelRow[];
  pending_add_model_ids: string[];
  action: AddModelAction;
  week_id: string;
  focus_task: string;
  events: WeeklyUsageEvent[];
  /**
   * Decision-tree models for projection. When omitted, derived from inventory
   * model ids (zero projected cost honesty — unknown costs stay null).
   */
  decision_models?: ModelOption[] | null;
  selected_model_id?: string | null;
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  existing_tasks?: string[] | null;
  proposed_new_tasks?: TaskFamilySeed[] | null;
  operator_ack: boolean;
  min_events_for_recommendation?: number;
  require_both?: boolean;
}

export interface SettingsAddModelBenchDecisionCompose {
  week_id: string;
  focus_task: string;
  add_model: SettingsAddModelInventoryCompose;
  bench_rec: AntiekBenchTaskModelRecommendationCompose;
  pack_ready: boolean;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_meter_read: false;
  suite_rewritten: false;
  backlog_mutated: false;
  store_mutated: false;
  notes: string[];
  authority: "settings_add_model_bench_decision_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function inventoryToDecisionModels(
  models: InventoryModelRow[],
  pending: string[],
  decision_models: ModelOption[] | null | undefined,
): ModelOption[] {
  if (decision_models != null) {
    if (!Array.isArray(decision_models) || decision_models.length === 0) {
      throw new Error("decision_models must be a non-empty array when set");
    }
    return decision_models;
  }
  const ids = new Set<string>();
  for (const m of models) {
    ids.add(m.model_id);
  }
  for (const p of pending) {
    if (p.trim()) ids.add(p.trim());
  }
  if (ids.size === 0) {
    throw new Error("models inventory or pending_add_model_ids required");
  }
  // Unknown projected costs — honesty: omit numbers (undefined).
  return Array.from(ids).map((model_id) => ({ model_id }));
}

/**
 * Compose add-model inventory pack with Antiek-bench decision tree recommend.
 * Never stores secrets; never mutates inventory; never auto-routes.
 */
export function composeSettingsAddModelBenchDecision(
  input: SettingsAddModelBenchDecisionInput,
): SettingsAddModelBenchDecisionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const week_id = requireNonEmpty(input.week_id, "week_id");
  const focus_task = requireNonEmpty(input.focus_task, "focus_task");

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "secrets_stored=false — BYOK inventory ids only",
    "inventory_mutated=false — pure propose only",
    "live_router_authorized=false — operator selects model",
    "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
  ];

  const add_model = composeSettingsAddModelInventory({
    models: input.models,
    pending_add_model_ids: input.pending_add_model_ids,
    action: input.action,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    selected_model_id: input.selected_model_id,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    operator_ack: input.operator_ack,
  });
  notes.push(...add_model.notes.map((n) => `[add_model] ${n}`));

  const decision_models = inventoryToDecisionModels(
    input.models,
    input.pending_add_model_ids,
    input.decision_models,
  );
  notes.push(`decision_models=${decision_models.length}`);

  const bench_rec = composeAntiekBenchTaskModelRecommendation({
    week_id,
    focus_task,
    events: input.events,
    models: decision_models,
    selected_model_id: input.selected_model_id,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    existing_tasks: input.existing_tasks,
    proposed_new_tasks: input.proposed_new_tasks,
    operator_ack: input.operator_ack,
    min_events_for_recommendation: input.min_events_for_recommendation,
  });
  notes.push(...bench_rec.notes.map((n) => `[bench_rec] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      add_model.pack_ready === true &&
      bench_rec.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (add_model.pack_ready === true || bench_rec.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — add-model inventory + bench decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — add_model, bench_rec, or operator_ack gate open",
    );
  }

  if (
    add_model.secrets_stored !== false ||
    add_model.inventory_mutated !== false ||
    add_model.live_router_authorized !== false ||
    bench_rec.live_router_authorized !== false ||
    bench_rec.secrets_stored !== false ||
    bench_rec.suite_rewritten !== false ||
    bench_rec.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("suite_rewritten=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");

  return {
    week_id,
    focus_task,
    add_model,
    bench_rec,
    pack_ready,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_meter_read: false,
    suite_rewritten: false,
    backlog_mutated: false,
    store_mutated: false,
    notes,
    authority: "settings_add_model_bench_decision_compose_advisory",
  };
}

export function formatSettingsAddModelBenchDecisionSummary(
  c: SettingsAddModelBenchDecisionCompose,
): string {
  const rec = c.bench_rec.recommendation?.recommended_model_id ?? "none";
  return (
    `pack_ready=${c.pack_ready} · ` +
    `add_ready=${c.add_model.pack_ready} · ` +
    `bench_ready=${c.bench_rec.pack_ready} · ` +
    `recommend=${rec} · ` +
    `would_exceed=${c.bench_rec.decision_tree.would_exceed} · ` +
    `secrets_stored=false · live_router_authorized=false · inventory_mutated=false`
  );
}
