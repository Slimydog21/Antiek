/**
 * Settings add-model + Antiek-bench decision + NotDiamond shadow (pure).
 *
 * Operator vision: BYOK add-model inventory, Antiek-bench task recommend,
 * decision-tree usage bar + prompt projection, and NotDiamond as shadow only
 * (§16 REJECT production router). Full settings model-quality surface without
 * auto-routing or secret storage.
 *
 * production_router_verdict always "REJECT".
 * live_router_authorized / secrets_stored / inventory_mutated always false.
 */

import {
  composeSettingsAddModelBenchDecision,
  type SettingsAddModelBenchDecisionCompose,
  type SettingsAddModelBenchDecisionInput,
  type AddModelAction,
} from "./settingsAddModelBenchDecisionCompose";
import {
  composeNotDiamondShadowAdvisory,
  type NotDiamondShadowAdvisoryCompose,
} from "./notDiamondShadowAdvisoryCompose";
import type { InventoryModelRow } from "./settingsModelInventoryBudgetCompose";
import type { WeeklyUsageEvent } from "./antiekBenchWeeklyUsageLearnCompose";
import type { TaskFamilySeed } from "./antiekBenchTaskFamilyExpandCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";

export type { AddModelAction };

export interface SettingsAddModelBenchNdShadowInput {
  models: InventoryModelRow[];
  pending_add_model_ids: string[];
  action: AddModelAction;
  week_id: string;
  focus_task: string;
  events: WeeklyUsageEvent[];
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
  /** ND recommended model (caller-supplied shadow log only). */
  nd_recommended_model_id: string | null;
  /** Default production: kill switch on unless operator opts into shadow. */
  kill_switch_on: boolean;
  nd_confidence?: number | null;
  require_both?: boolean;
}

export interface SettingsAddModelBenchNdShadowCompose {
  week_id: string;
  focus_task: string;
  settings_pack: SettingsAddModelBenchDecisionCompose;
  nd_shadow: NotDiamondShadowAdvisoryCompose;
  operator_selected_model_id: string;
  /**
   * Soft compare: bench recommendation vs ND shadow vs operator selection.
   * Never mutates selection.
   */
  bench_vs_nd: "agree" | "disagree" | "nd_hidden" | "bench_none";
  pack_ready: boolean;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  suite_rewritten: false;
  store_mutated: false;
  notes: string[];
  authority: "settings_add_model_bench_nd_shadow_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose add-model + bench decision tree + NotDiamond shadow pack.
 * ND never becomes live router (production_router_verdict=REJECT).
 */
export function composeSettingsAddModelBenchNdShadow(
  input: SettingsAddModelBenchNdShadowInput,
): SettingsAddModelBenchNdShadowCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.kill_switch_on !== "boolean") {
    throw new Error("kill_switch_on must be an explicit boolean");
  }
  const week_id = requireNonEmpty(input.week_id, "week_id");
  const focus_task = requireNonEmpty(input.focus_task, "focus_task");

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
    "live_router_authorized=false — operator selects model",
    "secrets_stored=false · inventory_mutated=false",
    "suite_rewritten=false · store_mutated=false",
  ];

  const settingsInput: SettingsAddModelBenchDecisionInput = {
    models: input.models,
    pending_add_model_ids: input.pending_add_model_ids,
    action: input.action,
    week_id,
    focus_task,
    events: input.events,
    decision_models: input.decision_models,
    selected_model_id: input.selected_model_id,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    existing_tasks: input.existing_tasks,
    proposed_new_tasks: input.proposed_new_tasks,
    operator_ack: input.operator_ack,
    min_events_for_recommendation: input.min_events_for_recommendation,
    require_both: true,
  };

  const settings_pack = composeSettingsAddModelBenchDecision(settingsInput);
  notes.push(...settings_pack.notes.map((n) => `[settings_pack] ${n}`));

  const operator_selected_model_id =
    settings_pack.bench_rec.decision_tree.driver.decision.selected_model_id;

  const inventory_ids = new Set<string>();
  for (const m of input.models) {
    inventory_ids.add(m.model_id);
  }
  for (const p of input.pending_add_model_ids) {
    if (p.trim()) inventory_ids.add(p.trim());
  }
  if (input.decision_models) {
    for (const m of input.decision_models) {
      inventory_ids.add(m.model_id);
    }
  }

  const nd_shadow = composeNotDiamondShadowAdvisory({
    selected_model_id: operator_selected_model_id,
    nd_recommended_model_id: input.nd_recommended_model_id,
    kill_switch_on: input.kill_switch_on,
    confidence: input.nd_confidence,
    task: focus_task,
    inventory_model_ids: Array.from(inventory_ids),
  });
  notes.push(...nd_shadow.notes.map((n) => `[nd] ${n}`));

  let bench_vs_nd: SettingsAddModelBenchNdShadowCompose["bench_vs_nd"];
  if (!nd_shadow.shadow_visible) {
    bench_vs_nd = "nd_hidden";
    notes.push("bench_vs_nd=nd_hidden — kill switch on or no valid ND rec");
  } else if (settings_pack.bench_rec.recommendation == null) {
    bench_vs_nd = "bench_none";
    notes.push("bench_vs_nd=bench_none — insufficient usage for task rec");
  } else if (
    settings_pack.bench_rec.recommendation.recommended_model_id ===
    nd_shadow.nd_recommended_model_id
  ) {
    bench_vs_nd = "agree";
    notes.push(
      "bench_vs_nd=agree — bench and ND shadow recommend same model (still advisory)",
    );
  } else {
    bench_vs_nd = "disagree";
    notes.push(
      `bench_vs_nd=disagree — bench=${settings_pack.bench_rec.recommendation.recommended_model_id} nd=${nd_shadow.nd_recommended_model_id} operator=${operator_selected_model_id}`,
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      settings_pack.pack_ready === true &&
      nd_shadow.live_router_authorized === false &&
      nd_shadow.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (settings_pack.pack_ready === true ||
        (nd_shadow.production_router_verdict === "REJECT" &&
          nd_shadow.live_router_authorized === false));
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — add-model+bench+ND shadow surface ready; still no live router",
    );
  } else {
    notes.push(
      "pack_ready=false — settings pack, ND invariant, or operator_ack gate open",
    );
  }

  if (
    settings_pack.live_router_authorized !== false ||
    settings_pack.secrets_stored !== false ||
    settings_pack.inventory_mutated !== false ||
    nd_shadow.live_router_authorized !== false ||
    nd_shadow.production_router_verdict !== "REJECT"
  ) {
    throw new Error(
      "invariant: ND must remain REJECT; live_router/secrets/inventory honesty false",
    );
  }

  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("suite_rewritten=false");
  notes.push("store_mutated=false");

  return {
    week_id,
    focus_task,
    settings_pack,
    nd_shadow,
    operator_selected_model_id,
    bench_vs_nd,
    pack_ready,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    suite_rewritten: false,
    store_mutated: false,
    notes,
    authority: "settings_add_model_bench_nd_shadow_compose_advisory",
  };
}

export function formatSettingsAddModelBenchNdShadowSummary(
  c: SettingsAddModelBenchNdShadowCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · task=${c.focus_task} · ` +
    `operator=${c.operator_selected_model_id} · bench_vs_nd=${c.bench_vs_nd} · ` +
    `would_exceed=${c.settings_pack.bench_rec.decision_tree.would_exceed} · ` +
    `production_router_verdict=REJECT · live_router_authorized=false · inventory_mutated=false`
  );
}
