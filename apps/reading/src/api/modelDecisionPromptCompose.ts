/**
 * Model decision + prompt budget projection compose (pure).
 *
 * Operator vision: choose a model for a prompt and see how it would affect
 * remaining budget before send. Composes usage-bar + projection pure math.
 *
 * would_exceed is null when remaining or high cost unknown (never invents safe).
 * Never calls providers or live meters.
 */

import {
  computeUsageBar,
  projectPromptAgainstBar,
  type PromptProjection,
  type UsageBarSnapshot,
} from "./promptProjection";

export interface ModelOption {
  model_id: string;
  tier?: string;
  /** Optional static cost estimate high for the proposed prompt. */
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
}

export interface ModelDecisionPromptComposeInput {
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  /**
   * Optional override projection costs (if model option lacks them).
   * Blank/unknown stays null — never invent $0.
   */
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
}

export interface ModelDecisionPromptComposeResult {
  selected_model_id: string;
  selected_tier: string | null;
  bar: UsageBarSnapshot;
  projection: PromptProjection;
  /** Mirror of projection.would_exceed for convenience. */
  would_exceed: boolean | null;
  notes: string[];
  authority: "model_decision_prompt_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose selected model + usage bar + prompt projection.
 * Fail closed if selected model not in inventory.
 */
export function composeModelDecisionWithProjection(
  input: ModelDecisionPromptComposeInput,
): ModelDecisionPromptComposeResult {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const selected = requireNonEmpty(
    input.selected_model_id,
    "selected_model_id",
  );
  if (!Array.isArray(input.models) || input.models.length === 0) {
    throw new Error("models must be a non-empty array");
  }

  let match: ModelOption | null = null;
  for (let i = 0; i < input.models.length; i++) {
    const m = input.models[i];
    if (!m || typeof m !== "object") {
      throw new Error(`models[${i}] must be an object`);
    }
    const id = requireNonEmpty(m.model_id, `models[${i}].model_id`);
    if (id === selected) {
      match = m;
    }
  }
  if (!match) {
    throw new Error(
      `selected_model_id ${selected} not found in models inventory`,
    );
  }

  const notes: string[] = [
    "advisory compose — no live meters, no provider dispatch",
  ];

  const bar = computeUsageBar({
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
  });

  // Prefer explicit input overrides, else model option, else null (unknown).
  const high =
    input.projected_cost_usd_high !== undefined
      ? input.projected_cost_usd_high
      : match.projected_cost_usd_high !== undefined
        ? match.projected_cost_usd_high
        : null;
  const low =
    input.projected_cost_usd_low !== undefined
      ? input.projected_cost_usd_low
      : match.projected_cost_usd_low !== undefined
        ? match.projected_cost_usd_low
        : null;

  const projection = projectPromptAgainstBar(bar, {
    projected_cost_usd_low: low ?? null,
    projected_cost_usd_high: high ?? null,
  });

  notes.push(...bar.notes);
  notes.push(...projection.notes);
  notes.push(`selected_model_id=${selected}`);

  return {
    selected_model_id: selected,
    selected_tier:
      typeof match.tier === "string" && match.tier.trim()
        ? match.tier.trim()
        : null,
    bar,
    projection,
    would_exceed: projection.would_exceed,
    notes,
    authority: "model_decision_prompt_compose_advisory",
  };
}

export function formatComposeSummary(
  r: ModelDecisionPromptComposeResult,
): string {
  const w =
    r.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${r.would_exceed}`;
  return `model=${r.selected_model_id} · ${w} · advisory`;
}
