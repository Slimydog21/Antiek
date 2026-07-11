/**
 * NotDiamond + Antiek-bench decision shadow pack (pure).
 *
 * Platform §16: NotDiamond is REJECTED as production router. This pack places
 * ND shadow next to Antiek-bench task model recommendation and the operator
 * decision tree so quality signals are visible without auto-routing.
 *
 * production_router_verdict always "REJECT".
 * live_router_authorized always false.
 * secrets_stored always false.
 * suite_rewritten always false.
 */

import {
  composeNotDiamondShadowAdvisory,
  type NotDiamondShadowAdvisoryCompose,
} from "./notDiamondShadowAdvisoryCompose";
import {
  composeAntiekBenchTaskModelRecommendation,
  type AntiekBenchTaskModelRecommendationCompose,
  type AntiekBenchTaskModelRecommendationInput,
} from "./antiekBenchTaskModelRecommendationCompose";
import type { WeeklyUsageEvent } from "./antiekBenchWeeklyUsageLearnCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type { TaskFamilySeed } from "./antiekBenchTaskFamilyExpandCompose";

export interface NotDiamondBenchDecisionShadowInput {
  week_id: string;
  focus_task: string;
  events: WeeklyUsageEvent[];
  models: ModelOption[];
  selected_model_id?: string | null;
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  existing_tasks?: string[] | null;
  proposed_new_tasks?: TaskFamilySeed[] | null;
  /**
   * ND recommended model (caller-supplied shadow log only).
   * Never invented.
   */
  nd_recommended_model_id: string | null;
  /**
   * Default true — production posture keeps ND kill switch on unless operator
   * explicitly opts into shadow display.
   */
  kill_switch_on: boolean;
  nd_confidence?: number | null;
  operator_ack: boolean;
  min_events_for_recommendation?: number;
}

export interface NotDiamondBenchDecisionShadowCompose {
  week_id: string;
  focus_task: string;
  bench_rec: AntiekBenchTaskModelRecommendationCompose;
  nd_shadow: NotDiamondShadowAdvisoryCompose;
  /**
   * Operator-facing selection (from bench pack decision tree).
   * Never auto-switched to ND suggestion.
   */
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
  suite_rewritten: false;
  notes: string[];
  authority: "notdiamond_bench_decision_shadow_compose_advisory";
}

/**
 * Compose Antiek-bench model rec + NotDiamond shadow + decision tree pack.
 * ND never becomes live router (production_router_verdict=REJECT).
 */
export function composeNotDiamondBenchDecisionShadow(
  input: NotDiamondBenchDecisionShadowInput,
): NotDiamondBenchDecisionShadowCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.kill_switch_on !== "boolean") {
    throw new Error("kill_switch_on must be an explicit boolean");
  }

  const notes: string[] = [
    "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
    "live_router_authorized=false — operator selects model",
    "secrets_stored=false",
    "suite_rewritten=false — bench rec is advisory only",
  ];

  const benchInput: AntiekBenchTaskModelRecommendationInput = {
    week_id: input.week_id,
    focus_task: input.focus_task,
    events: input.events,
    models: input.models,
    selected_model_id: input.selected_model_id,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    existing_tasks: input.existing_tasks,
    proposed_new_tasks: input.proposed_new_tasks,
    operator_ack: input.operator_ack,
    min_events_for_recommendation: input.min_events_for_recommendation,
  };

  const bench_rec = composeAntiekBenchTaskModelRecommendation(benchInput);
  notes.push(...bench_rec.notes.map((n) => `[bench] ${n}`));

  const operator_selected_model_id =
    bench_rec.decision_tree.driver.decision.selected_model_id;

  const inventory = input.models.map((m) => m.model_id);
  const nd_shadow = composeNotDiamondShadowAdvisory({
    selected_model_id: operator_selected_model_id,
    nd_recommended_model_id: input.nd_recommended_model_id,
    kill_switch_on: input.kill_switch_on,
    confidence: input.nd_confidence,
    task: input.focus_task,
    inventory_model_ids: inventory,
  });
  notes.push(...nd_shadow.notes.map((n) => `[nd] ${n}`));

  let bench_vs_nd: NotDiamondBenchDecisionShadowCompose["bench_vs_nd"];
  if (!nd_shadow.shadow_visible) {
    bench_vs_nd = "nd_hidden";
    notes.push("bench_vs_nd=nd_hidden — kill switch on or no valid ND rec");
  } else if (bench_rec.recommendation == null) {
    bench_vs_nd = "bench_none";
    notes.push("bench_vs_nd=bench_none — insufficient usage for task rec");
  } else if (
    bench_rec.recommendation.recommended_model_id ===
    nd_shadow.nd_recommended_model_id
  ) {
    bench_vs_nd = "agree";
    notes.push(
      "bench_vs_nd=agree — bench and ND shadow recommend same model (still advisory)",
    );
  } else {
    bench_vs_nd = "disagree";
    notes.push(
      `bench_vs_nd=disagree — bench=${bench_rec.recommendation.recommended_model_id} nd=${nd_shadow.nd_recommended_model_id} operator=${operator_selected_model_id}`,
    );
  }

  const pack_ready =
    bench_rec.pack_ready === true &&
    nd_shadow.live_router_authorized === false &&
    nd_shadow.production_router_verdict === "REJECT" &&
    input.operator_ack === true;

  if (pack_ready) {
    notes.push(
      "pack_ready=true — bench+ND shadow decision surface ready; still no live router",
    );
  } else {
    notes.push("pack_ready=false — bench pack or operator_ack gate open");
  }

  if (
    bench_rec.live_router_authorized !== false ||
    nd_shadow.live_router_authorized !== false ||
    nd_shadow.production_router_verdict !== "REJECT"
  ) {
    throw new Error(
      "invariant: ND must remain REJECT and live_router_authorized false",
    );
  }

  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");

  return {
    week_id: input.week_id,
    focus_task: input.focus_task,
    bench_rec,
    nd_shadow,
    operator_selected_model_id,
    bench_vs_nd,
    pack_ready,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    secrets_stored: false,
    suite_rewritten: false,
    notes,
    authority: "notdiamond_bench_decision_shadow_compose_advisory",
  };
}

export function formatNotDiamondBenchDecisionShadowSummary(
  c: NotDiamondBenchDecisionShadowCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · task=${c.focus_task} · ` +
    `operator=${c.operator_selected_model_id} · bench_vs_nd=${c.bench_vs_nd} · ` +
    `production_router_verdict=REJECT · live_router_authorized=false`
  );
}
