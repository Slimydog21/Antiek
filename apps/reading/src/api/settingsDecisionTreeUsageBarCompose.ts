/**
 * Settings decision-tree + usage bar pack compose (pure).
 *
 * Operator vision: model decision tree tab with usage bar against budget
 * limit and projection of how the proposed prompt would affect that limit.
 * Composes settings model driver tab; never live-routes or stores secrets.
 *
 * live_router_authorized always false.
 * secrets_stored always false.
 * live_meter_read always false.
 */

import {
  composeSettingsModelDriverTab,
  type BenchTaskBest,
  type NotDiamondShadowRec,
  type SettingsModelDriverTabCompose,
  type SettingsModelDriverTabInput,
} from "./settingsModelDriverTabCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";

export interface SettingsDecisionTreeUsageBarInput {
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  pending_add_model_ids?: string[] | null;
  operator_ack: boolean;
}

export interface SettingsDecisionTreeUsageBarCompose {
  driver: SettingsModelDriverTabCompose;
  /** fraction_used * 100 when known; null when unknown (never invent 0). */
  usage_percent: number | null;
  remaining_usd: number | null;
  would_exceed: boolean | null;
  remaining_after_high_usd: number | null;
  /**
   * True when tab_ready and operator_ack. Still never routes live.
   */
  decision_ready: boolean;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  notes: string[];
  authority: "settings_decision_tree_usage_bar_compose_advisory";
}

/**
 * Compose decision-tree surface pack: model selection + usage bar + prompt impact.
 */
export function composeSettingsDecisionTreeUsageBar(
  input: SettingsDecisionTreeUsageBarInput,
): SettingsDecisionTreeUsageBarCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }

  const notes: string[] = [
    "live_router_authorized=false — operator selects model",
    "secrets_stored=false — inventory ids only",
    "live_meter_read=false — bar/projection are pure advisory math",
  ];

  const tabInput: SettingsModelDriverTabInput = {
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task,
    nd_shadow: input.nd_shadow,
    pending_add_model_ids: input.pending_add_model_ids,
  };
  const driver = composeSettingsModelDriverTab(tabInput);
  notes.push(...driver.notes);

  const bar = driver.decision.bar;
  const projection = driver.decision.projection;

  let usage_percent: number | null = null;
  if (bar.fraction_used !== null) {
    usage_percent = bar.fraction_used * 100;
    if (!Number.isFinite(usage_percent)) {
      throw new Error("usage_percent overflowed to non-finite");
    }
    notes.push(`usage_percent=${usage_percent.toFixed(2)} (advisory display)`);
  } else {
    notes.push(
      "usage_percent=null — cap/spent unknown (never invent 0% used)",
    );
  }

  const remaining_usd = bar.remaining_usd;
  const would_exceed = driver.decision.would_exceed;
  const remaining_after_high_usd = projection.remaining_after_high_usd;

  if (would_exceed === null) {
    notes.push(
      "would_exceed=null — projection incomplete (remaining or high cost unknown)",
    );
  } else if (would_exceed) {
    notes.push(
      "would_exceed=true — proposed prompt would exceed remaining budget",
    );
  } else {
    notes.push("would_exceed=false — projected high cost fits remaining");
  }

  const decision_ready = driver.tab_ready && input.operator_ack;
  if (!driver.tab_ready) {
    notes.push("decision_ready=false — driver tab not ready");
  } else if (!input.operator_ack) {
    notes.push("decision_ready=false — operator_ack required");
  } else {
    notes.push(
      "decision_ready=true — operator may proceed; still live_router_authorized=false",
    );
  }

  if (driver.live_router_authorized !== false || driver.secrets_stored !== false) {
    throw new Error("invariant: driver honesty flags must remain false");
  }

  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");

  return {
    driver,
    usage_percent,
    remaining_usd,
    would_exceed,
    remaining_after_high_usd,
    decision_ready,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    notes,
    authority: "settings_decision_tree_usage_bar_compose_advisory",
  };
}

export function formatSettingsDecisionTreeUsageBarSummary(
  c: SettingsDecisionTreeUsageBarCompose,
): string {
  const pct =
    c.usage_percent === null ? "usage%=null" : `usage%=${c.usage_percent.toFixed(1)}`;
  const w =
    c.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${c.would_exceed}`;
  return (
    `decision_ready=${c.decision_ready} · model=${c.driver.decision.selected_model_id} · ` +
    `${pct} · ${w} · live_router_authorized=false · secrets_stored=false · live_meter_read=false`
  );
}
