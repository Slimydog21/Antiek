/**
 * Settings model driver tab compose (pure).
 *
 * Operator vision: decision-tree tab to select the AI model for a prompt,
 * with usage bar, budget projection, optional Antiek-bench weekly best,
 * and optional NotDiamond shadow recommendation (never authority).
 *
 * live_router_authorized always false.
 * secrets_stored always false (add-model is inventory-only here).
 */

import {
  composeModelDecisionWithProjection,
  type ModelDecisionPromptComposeInput,
  type ModelDecisionPromptComposeResult,
  type ModelOption,
} from "./modelDecisionPromptCompose";

export interface BenchTaskBest {
  /** Task family (e.g. deep_research, twin_notes). */
  task: string;
  /** Model id ranked best for task — caller-supplied only. */
  best_model_id: string;
  /** Optional score 0..1. */
  score?: number | null;
}

export interface NotDiamondShadowRec {
  /** ND recommended model id — advisory shadow only. */
  recommended_model_id: string;
  /** Kill switch must be off for ND to be considered shown. */
  kill_switch_on: boolean;
  confidence?: number | null;
}

export interface SettingsModelDriverTabInput {
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  /**
   * Optional Antiek-bench weekly bests (caller-supplied rankings only).
   * Never invents leaderboard rows.
   */
  bench_bests?: BenchTaskBest[] | null;
  /** Optional task to highlight for bench alignment. */
  focus_task?: string | null;
  /**
   * Optional NotDiamond shadow rec. Never becomes routing authority.
   */
  nd_shadow?: NotDiamondShadowRec | null;
  /**
   * Models pending add (BYOK inventory rows without secret material).
   * Secrets must not appear here — secrets_stored stays false.
   */
  pending_add_model_ids?: string[] | null;
}

export interface SettingsModelDriverTabCompose {
  decision: ModelDecisionPromptComposeResult;
  inventory_count: number;
  pending_add_count: number;
  /** True when selected model matches bench best for focus_task (if set). */
  bench_aligned: boolean | null;
  bench_best_for_focus: string | null;
  /** True when ND shadow recommends a different model and kill_switch off. */
  nd_shadow_differs: boolean | null;
  nd_shadow_model: string | null;
  /**
   * Tab ready for operator decision when inventory non-empty and decision
   * composed (would_exceed may still be null — honesty).
   */
  tab_ready: boolean;
  /** Always false — ND/local never auto-route from this surface. */
  live_router_authorized: false;
  /** Always false — no secret material accepted or stored. */
  secrets_stored: false;
  notes: string[];
  authority: "settings_model_driver_tab_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose the settings model-driver decision tree tab snapshot.
 * Never authorizes live routing; never stores secrets.
 */
export function composeSettingsModelDriverTab(
  input: SettingsModelDriverTabInput,
): SettingsModelDriverTabCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }

  const notes: string[] = [
    "live_router_authorized=false — operator selects model; no auto-router",
    "secrets_stored=false — inventory/ids only; never accept raw API keys here",
    "NotDiamond is advisory/shadow only (§16 REJECT as production router)",
  ];

  const decisionInput: ModelDecisionPromptComposeInput = {
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
  };
  const decision = composeModelDecisionWithProjection(decisionInput);
  notes.push(...decision.notes);

  const inventory_count = input.models.length;
  notes.push(`inventory_count=${inventory_count}`);

  let pending_add_count = 0;
  if (input.pending_add_model_ids != null) {
    if (!Array.isArray(input.pending_add_model_ids)) {
      throw new Error("pending_add_model_ids must be an array when set");
    }
    const seen = new Set<string>();
    for (let i = 0; i < input.pending_add_model_ids.length; i++) {
      const id = requireNonEmpty(
        input.pending_add_model_ids[i],
        `pending_add_model_ids[${i}]`,
      );
      // Reject anything that looks like a secret (fail closed).
      if (
        id.length > 128 ||
        /sk-|api[_-]?key|secret|bearer\s/i.test(id) ||
        id.includes(" ")
      ) {
        throw new Error(
          `pending_add_model_ids[${i}] must be a model id, not secret material`,
        );
      }
      if (seen.has(id)) {
        throw new Error(`duplicate pending_add_model_id: ${id}`);
      }
      seen.add(id);
    }
    pending_add_count = seen.size;
    notes.push(`pending_add_count=${pending_add_count} (ids only, no secrets)`);
  }

  let bench_aligned: boolean | null = null;
  let bench_best_for_focus: string | null = null;
  if (input.bench_bests != null) {
    if (!Array.isArray(input.bench_bests)) {
      throw new Error("bench_bests must be an array when set");
    }
    const focus =
      input.focus_task === undefined || input.focus_task === null
        ? null
        : requireNonEmpty(input.focus_task, "focus_task");
    if (input.bench_bests.length === 0) {
      notes.push("bench_bests empty — no invent leaderboard");
    }
    for (let i = 0; i < input.bench_bests.length; i++) {
      const b = input.bench_bests[i];
      if (!b || typeof b !== "object") {
        throw new Error(`bench_bests[${i}] must be an object`);
      }
      const task = requireNonEmpty(b.task, `bench_bests[${i}].task`);
      const best = requireNonEmpty(
        b.best_model_id,
        `bench_bests[${i}].best_model_id`,
      );
      if (b.score !== undefined && b.score !== null) {
        if (
          typeof b.score !== "number" ||
          !Number.isFinite(b.score) ||
          b.score < 0 ||
          b.score > 1
        ) {
          throw new Error(
            `bench_bests[${i}].score must be finite in [0, 1] when set`,
          );
        }
      }
      if (focus !== null && task === focus) {
        bench_best_for_focus = best;
        bench_aligned = best === decision.selected_model_id;
        notes.push(
          bench_aligned
            ? `bench_aligned=true for task=${focus}`
            : `bench_aligned=false (selected=${decision.selected_model_id} best=${best})`,
        );
      }
    }
    if (focus !== null && bench_best_for_focus === null) {
      notes.push(
        `focus_task=${focus} not in bench_bests — bench_aligned=null (no invent)`,
      );
    }
  } else if (input.focus_task != null) {
    notes.push("focus_task set without bench_bests — bench_aligned=null");
  }

  let nd_shadow_differs: boolean | null = null;
  let nd_shadow_model: string | null = null;
  if (input.nd_shadow != null) {
    if (typeof input.nd_shadow !== "object") {
      throw new Error("nd_shadow must be an object when set");
    }
    if (typeof input.nd_shadow.kill_switch_on !== "boolean") {
      throw new Error("nd_shadow.kill_switch_on must be an explicit boolean");
    }
    const rec = requireNonEmpty(
      input.nd_shadow.recommended_model_id,
      "nd_shadow.recommended_model_id",
    );
    if (input.nd_shadow.kill_switch_on) {
      notes.push(
        "nd_shadow kill_switch_on=true — shadow suppressed (default off required)",
      );
      nd_shadow_differs = null;
      nd_shadow_model = null;
    } else {
      nd_shadow_model = rec;
      nd_shadow_differs = rec !== decision.selected_model_id;
      notes.push(
        nd_shadow_differs
          ? `nd_shadow_differs=true (shadow=${rec}, selected=${decision.selected_model_id}) — advisory only`
          : `nd_shadow_differs=false (shadow agrees with selected) — still not authority`,
      );
    }
    if (
      input.nd_shadow.confidence !== undefined &&
      input.nd_shadow.confidence !== null
    ) {
      if (
        typeof input.nd_shadow.confidence !== "number" ||
        !Number.isFinite(input.nd_shadow.confidence) ||
        input.nd_shadow.confidence < 0 ||
        input.nd_shadow.confidence > 1
      ) {
        throw new Error(
          "nd_shadow.confidence must be finite in [0, 1] when set",
        );
      }
    }
  }

  const tab_ready = inventory_count >= 1;
  notes.push(
    tab_ready
      ? "tab_ready=true — inventory present for operator selection"
      : "tab_ready=false — empty inventory",
  );
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");

  return {
    decision,
    inventory_count,
    pending_add_count,
    bench_aligned,
    bench_best_for_focus,
    nd_shadow_differs,
    nd_shadow_model,
    tab_ready,
    live_router_authorized: false,
    secrets_stored: false,
    notes,
    authority: "settings_model_driver_tab_compose_advisory",
  };
}

export function formatSettingsModelDriverTabSummary(
  t: SettingsModelDriverTabCompose,
): string {
  const w =
    t.decision.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${t.decision.would_exceed}`;
  return (
    `driver tab · model=${t.decision.selected_model_id} · ${w} · ` +
    `tab_ready=${t.tab_ready} · live_router_authorized=false · secrets_stored=false`
  );
}
