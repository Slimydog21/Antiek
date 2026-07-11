/**
 * Antiek-bench task → model recommendation compose (pure).
 *
 * Operator vision: recursive Antiek-bench learns from weekly usage what
 * models work for which tasks, then surfaces a recommendation into the
 * model decision tree (with usage bar + prompt projection) so the operator
 * can optimize model quality per task — never auto-routes live.
 *
 * live_router_authorized always false.
 * secrets_stored always false.
 * live_meter_read always false.
 * backlog_mutated / store_mutated / suite_rewritten always false.
 */

import {
  composeAntiekBenchTaskFamilyExpand,
  type AntiekBenchTaskFamilyExpandCompose,
  type TaskFamilySeed,
} from "./antiekBenchTaskFamilyExpandCompose";
import type { WeeklyUsageEvent } from "./antiekBenchWeeklyUsageLearnCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type { BenchTaskBest } from "./settingsModelDriverTabCompose";
import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
} from "./settingsDecisionTreeUsageBarCompose";

export interface TaskModelRecommendation {
  task: string;
  recommended_model_id: string;
  /** Derived from usage: worked rate among events for task+model. */
  worked_rate: number | null;
  /** Average score when scores present; null if none. */
  avg_score: number | null;
  event_count: number;
  reason: string;
}

export interface AntiekBenchTaskModelRecommendationInput {
  week_id: string;
  focus_task: string;
  events: WeeklyUsageEvent[];
  models: ModelOption[];
  /**
   * Operator-selected model; if empty string omitted use recommended when known.
   * When provided, decision tree uses this selection (recommendation is advisory).
   */
  selected_model_id?: string | null;
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  existing_tasks?: string[] | null;
  proposed_new_tasks?: TaskFamilySeed[] | null;
  operator_ack: boolean;
  min_events_per_task?: number;
  /**
   * Minimum events for a model on the focus task before recommending it.
   * Default 2 when omitted.
   */
  min_events_for_recommendation?: number;
}

export interface AntiekBenchTaskModelRecommendationCompose {
  week_id: string;
  focus_task: string;
  expand: AntiekBenchTaskFamilyExpandCompose;
  /** Derived leaderboard from usage (caller events only). */
  task_bests: BenchTaskBest[];
  recommendation: TaskModelRecommendation | null;
  decision_tree: SettingsDecisionTreeUsageBarCompose;
  /**
   * True when recommendation present (or explicitly no-data path acknowledged)
   * and decision_tree.decision_ready.
   */
  pack_ready: boolean;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  notes: string[];
  authority: "antiek_bench_task_model_recommendation_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

interface ModelAgg {
  model_id: string;
  event_count: number;
  worked: number;
  score_sum: number;
  score_n: number;
}

/**
 * Derive model recommendations per task from weekly usage events only.
 * Never invents models or outcomes.
 */
function deriveTaskBests(
  events: WeeklyUsageEvent[],
  minEvents: number,
): { bests: BenchTaskBest[]; byTask: Map<string, TaskModelRecommendation[]> } {
  const byTaskModel = new Map<string, Map<string, ModelAgg>>();
  for (const e of events) {
    const task = e.task.trim();
    const mid = e.model_id.trim();
    if (!byTaskModel.has(task)) {
      byTaskModel.set(task, new Map());
    }
    const m = byTaskModel.get(task)!;
    if (!m.has(mid)) {
      m.set(mid, {
        model_id: mid,
        event_count: 0,
        worked: 0,
        score_sum: 0,
        score_n: 0,
      });
    }
    const a = m.get(mid)!;
    a.event_count += 1;
    if (e.outcome === "worked") {
      a.worked += 1;
    }
    if (e.score != null && typeof e.score === "number" && Number.isFinite(e.score)) {
      a.score_sum += e.score;
      a.score_n += 1;
    }
  }

  const byTask = new Map<string, TaskModelRecommendation[]>();
  const bests: BenchTaskBest[] = [];

  for (const [task, models] of byTaskModel) {
    const recs: TaskModelRecommendation[] = [];
    for (const a of models.values()) {
      if (a.event_count < minEvents) {
        continue;
      }
      const worked_rate = a.event_count > 0 ? a.worked / a.event_count : null;
      const avg_score = a.score_n > 0 ? a.score_sum / a.score_n : null;
      recs.push({
        task,
        recommended_model_id: a.model_id,
        worked_rate,
        avg_score,
        event_count: a.event_count,
        reason:
          avg_score != null
            ? `usage n=${a.event_count} worked_rate=${worked_rate?.toFixed(2)} avg_score=${avg_score.toFixed(2)}`
            : `usage n=${a.event_count} worked_rate=${worked_rate?.toFixed(2) ?? "n/a"}`,
      });
    }
    // Rank: higher worked_rate, then avg_score, then event_count
    recs.sort((x, y) => {
      const wr = (y.worked_rate ?? -1) - (x.worked_rate ?? -1);
      if (wr !== 0) return wr;
      const sc = (y.avg_score ?? -1) - (x.avg_score ?? -1);
      if (sc !== 0) return sc;
      return y.event_count - x.event_count;
    });
    byTask.set(task, recs);
    if (recs.length > 0) {
      const top = recs[0];
      bests.push({
        task,
        best_model_id: top.recommended_model_id,
        score: top.avg_score,
      });
    }
  }

  return { bests, byTask };
}

/**
 * Compose Antiek-bench usage-learn → task model recommendation → decision tree.
 * Never live-routes; never mutates bench store.
 */
export function composeAntiekBenchTaskModelRecommendation(
  input: AntiekBenchTaskModelRecommendationInput,
): AntiekBenchTaskModelRecommendationCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const week_id = requireNonEmpty(input.week_id, "week_id");
  const focus_task = requireNonEmpty(input.focus_task, "focus_task");
  if (!Array.isArray(input.events)) {
    throw new Error("events must be an array");
  }
  if (!Array.isArray(input.models) || input.models.length === 0) {
    throw new Error("models must be a non-empty array");
  }

  const minRec =
    input.min_events_for_recommendation === undefined ||
    input.min_events_for_recommendation === null
      ? 2
      : input.min_events_for_recommendation;
  if (
    typeof minRec !== "number" ||
    !Number.isFinite(minRec) ||
    minRec < 1 ||
    !Number.isInteger(minRec)
  ) {
    throw new Error("min_events_for_recommendation must be integer ≥ 1");
  }

  const notes: string[] = [
    "live_router_authorized=false — recommendation is advisory only",
    "secrets_stored=false",
    "live_meter_read=false",
    "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
  ];

  const existing =
    input.existing_tasks == null
      ? [focus_task]
      : input.existing_tasks;

  const expand = composeAntiekBenchTaskFamilyExpand({
    week_id,
    existing_tasks: existing,
    proposed_new_tasks: input.proposed_new_tasks,
    events: input.events,
    operator_ack: input.operator_ack,
    min_events_per_task: input.min_events_per_task,
  });
  notes.push(...expand.notes.map((n) => `[expand] ${n}`));

  const { bests, byTask } = deriveTaskBests(input.events, minRec);
  const focusRecs = byTask.get(focus_task) ?? [];
  const recommendation = focusRecs.length > 0 ? focusRecs[0] : null;
  if (recommendation == null) {
    notes.push(
      `no recommendation for focus_task=${focus_task} — need ≥${minRec} events per model (no invent)`,
    );
  } else {
    notes.push(
      `recommendation=${recommendation.recommended_model_id} for ${focus_task} · ${recommendation.reason}`,
    );
  }

  // Selected model: explicit selection wins; else recommended if in models; else first model
  const modelIds = new Set(
    input.models.map((m) => requireNonEmpty(m.model_id, "models[].model_id")),
  );
  let selected: string;
  if (
    input.selected_model_id != null &&
    String(input.selected_model_id).trim() !== ""
  ) {
    selected = requireNonEmpty(
      input.selected_model_id,
      "selected_model_id",
    );
    if (!modelIds.has(selected)) {
      throw new Error("selected_model_id must be in models");
    }
  } else if (
    recommendation != null &&
    modelIds.has(recommendation.recommended_model_id)
  ) {
    selected = recommendation.recommended_model_id;
    notes.push("selected_model_id defaulted to recommendation (advisory)");
  } else {
    selected = input.models[0].model_id.trim();
    notes.push(
      "selected_model_id defaulted to models[0] — no usable recommendation in inventory",
    );
  }

  const decision_tree = composeSettingsDecisionTreeUsageBar({
    selected_model_id: selected,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: bests,
    focus_task,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision_tree.notes.map((n) => `[decision] ${n}`));

  const pack_ready =
    decision_tree.decision_ready === true && input.operator_ack === true;
  if (pack_ready) {
    notes.push(
      "pack_ready=true — bench→recommendation→decision tree advisory pack; still no live route",
    );
  } else {
    notes.push("pack_ready=false — decision tree or operator_ack gate open");
  }

  notes.push("live_router_authorized=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");

  return {
    week_id,
    focus_task,
    expand,
    task_bests: bests,
    recommendation,
    decision_tree,
    pack_ready,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    notes,
    authority: "antiek_bench_task_model_recommendation_compose_advisory",
  };
}

export function formatAntiekBenchTaskModelRecommendationSummary(
  c: AntiekBenchTaskModelRecommendationCompose,
): string {
  const rec = c.recommendation?.recommended_model_id ?? "none";
  return (
    `pack_ready=${c.pack_ready} · focus=${c.focus_task} · rec=${rec} · ` +
    `selected=${c.decision_tree.driver.decision.selected_model_id} · ` +
    `live_router_authorized=false · suite_rewritten=false`
  );
}
