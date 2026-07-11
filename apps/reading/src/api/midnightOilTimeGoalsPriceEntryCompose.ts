/**
 * Midnight Oil time + goals + price ceiling entry compose (pure).
 *
 * Operator vision: set time of work and goals; system recommends a price
 * ceiling to approve — then unattended swarm can proceed under separate
 * launch authorization. This pure layer is the operator entry form only.
 *
 * live_execution_authorized always false.
 */

import {
  recommendMidnightOilPriceCeiling,
  type MidnightOilPriceCeilingRecommend,
} from "./midnightOilLaunchPackageCompose";

export interface MoGoalEntry {
  goal_id: string;
  title: string;
}

export interface MidnightOilTimeGoalsPriceEntryInput {
  operator_id: string;
  work_minutes: number;
  goals: MoGoalEntry[];
  /**
   * Optional blended USD/hour for recommendation.
   * Null = recommended ceiling stays null (no invent $0).
   */
  usd_per_hour?: number | null;
  /** Operator-approved ceiling after seeing recommendation; null = not yet. */
  approved_ceiling_usd?: number | null;
  operator_ack: boolean;
}

export interface MidnightOilTimeGoalsPriceEntryCompose {
  operator_id: string;
  work_minutes: number;
  goal_count: number;
  goal_ids: string[];
  recommend: MidnightOilPriceCeilingRecommend;
  approved_ceiling_usd: number | null;
  /**
   * True when operator_ack, ≥1 goal, work_minutes>0, and approved ceiling
   * is set when recommendation is known (or override path when rec null).
   */
  entry_ready: boolean;
  /** Always false — entry form never launches MO workers. */
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_time_goals_price_entry_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requirePositiveFinite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive finite number`);
  }
  return value;
}

/**
 * Compose MO operator entry: time + goals + recommended price ceiling.
 * Never authorizes unattended execution.
 */
export function composeMidnightOilTimeGoalsPriceEntry(
  input: MidnightOilTimeGoalsPriceEntryInput,
): MidnightOilTimeGoalsPriceEntryCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  const work_minutes = requirePositiveFinite(
    input.work_minutes,
    "work_minutes",
  );
  if (!Array.isArray(input.goals) || input.goals.length === 0) {
    throw new Error("goals must be a non-empty array");
  }

  const notes: string[] = [
    "live_execution_authorized=false — entry form never launches MO workers",
    "recommended ceiling is advisory; operator approval is separate",
  ];

  const goal_ids: string[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < input.goals.length; i++) {
    const g = input.goals[i];
    if (!g || typeof g !== "object") {
      throw new Error(`goals[${i}] must be an object`);
    }
    const id = requireNonEmpty(g.goal_id, `goals[${i}].goal_id`);
    requireNonEmpty(g.title, `goals[${i}].title`);
    if (seen.has(id)) {
      throw new Error(`duplicate goal_id: ${id}`);
    }
    seen.add(id);
    goal_ids.push(id);
  }
  const goal_count = goal_ids.length;
  notes.push(`goal_count=${goal_count} · work_minutes=${work_minutes}`);

  const recommend = recommendMidnightOilPriceCeiling({
    work_minutes,
    goal_count,
    usd_per_hour: input.usd_per_hour,
  });
  notes.push(...recommend.notes);

  let approved_ceiling_usd: number | null = null;
  if (
    input.approved_ceiling_usd !== undefined &&
    input.approved_ceiling_usd !== null
  ) {
    if (
      typeof input.approved_ceiling_usd !== "number" ||
      !Number.isFinite(input.approved_ceiling_usd) ||
      input.approved_ceiling_usd < 0
    ) {
      throw new Error(
        "approved_ceiling_usd must be non-negative finite when set",
      );
    }
    approved_ceiling_usd = input.approved_ceiling_usd;
    notes.push(`approved_ceiling_usd=${approved_ceiling_usd}`);
  } else {
    notes.push("approved_ceiling_usd=null — operator has not approved yet");
  }

  let entry_ready = false;
  if (!input.operator_ack) {
    notes.push("entry_ready=false — operator_ack required");
  } else if (recommend.recommended_ceiling_usd !== null) {
    if (approved_ceiling_usd === null) {
      notes.push(
        "entry_ready=false — recommended ceiling present; approve a ceiling first",
      );
    } else {
      entry_ready = true;
      notes.push(
        "entry_ready=true — time+goals+approved ceiling (still live_execution_authorized=false)",
      );
    }
  } else {
    // Recommendation unknown — allow entry with explicit approved ceiling only
    if (approved_ceiling_usd === null) {
      notes.push(
        "entry_ready=false — recommendation unknown and no approved ceiling",
      );
    } else {
      entry_ready = true;
      notes.push(
        "entry_ready=true — approved ceiling without recommended $ (honest null rec)",
      );
    }
  }

  notes.push("live_execution_authorized=false");

  return {
    operator_id,
    work_minutes,
    goal_count,
    goal_ids,
    recommend,
    approved_ceiling_usd,
    entry_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_time_goals_price_entry_compose_advisory",
  };
}

export function formatMidnightOilTimeGoalsPriceEntrySummary(
  c: MidnightOilTimeGoalsPriceEntryCompose,
): string {
  return (
    `entry_ready=${c.entry_ready} · minutes=${c.work_minutes} · goals=${c.goal_count} · ` +
    `rec=${c.recommend.recommended_ceiling_usd} · approved=${c.approved_ceiling_usd} · ` +
    `live_execution_authorized=false`
  );
}
