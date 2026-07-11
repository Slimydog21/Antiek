/**
 * Midnight Oil entry → swarm readiness supercompose (pure).
 *
 * Operator vision: set time + goals + approve price ceiling, then evaluate
 * unattended swarm readiness — without authorizing live workers.
 *
 * live_execution_authorized always false.
 */

import {
  composeMidnightOilTimeGoalsPriceEntry,
  type MidnightOilTimeGoalsPriceEntryCompose,
  type MoGoalEntry,
} from "./midnightOilTimeGoalsPriceEntryCompose";
import {
  evaluateMidnightOilSwarmReadiness,
  type MidnightOilSwarmReadinessDecision,
} from "./midnightOilSwarmReadiness";

export interface MidnightOilEntryToSwarmReadinessInput {
  operator_id: string;
  work_minutes: number;
  goals: MoGoalEntry[];
  usd_per_hour?: number | null;
  approved_ceiling_usd?: number | null;
  /** Entry form ack. */
  operator_ack: boolean;
  /** Swarm brief dispatch-ready (caller-supplied). */
  brief_dispatch_ready: boolean;
  /** Explicit unattended handoff ack. */
  unattended_ack: boolean;
  /** Spend consent when ceiling > 0. */
  spend_consent: boolean;
}

export interface MidnightOilEntryToSwarmReadinessCompose {
  entry: MidnightOilTimeGoalsPriceEntryCompose;
  readiness: MidnightOilSwarmReadinessDecision;
  /**
   * True when entry_ready and readiness unattended_ready (if field exists)
   * or equivalent readiness flag.
   */
  package_ready: boolean;
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_entry_to_swarm_readiness_compose_advisory";
}

/**
 * Compose MO entry + swarm readiness in one pure package.
 */
export function composeMidnightOilEntryToSwarmReadiness(
  input: MidnightOilEntryToSwarmReadinessInput,
): MidnightOilEntryToSwarmReadinessCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.brief_dispatch_ready !== "boolean") {
    throw new Error("brief_dispatch_ready must be an explicit boolean");
  }
  if (typeof input.unattended_ack !== "boolean") {
    throw new Error("unattended_ack must be an explicit boolean");
  }
  if (typeof input.spend_consent !== "boolean") {
    throw new Error("spend_consent must be an explicit boolean");
  }

  const notes: string[] = [
    "live_execution_authorized=false — entry+readiness package never launches workers",
  ];

  const entry = composeMidnightOilTimeGoalsPriceEntry({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goals: input.goals,
    usd_per_hour: input.usd_per_hour,
    approved_ceiling_usd: input.approved_ceiling_usd,
    operator_ack: input.operator_ack,
  });
  notes.push(...entry.notes);

  const readiness = evaluateMidnightOilSwarmReadiness({
    operator_id: entry.operator_id,
    work_minutes: entry.work_minutes,
    goal_count: entry.goal_count,
    price_ceiling_usd: entry.approved_ceiling_usd,
    recommended_ceiling_usd: entry.recommend.recommended_ceiling_usd,
    brief_dispatch_ready: input.brief_dispatch_ready,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
  });
  notes.push(...readiness.notes);

  const package_ready = entry.entry_ready && readiness.unattended_ready;
  if (!entry.entry_ready) {
    notes.push("package_ready=false — entry not ready");
  } else if (!readiness.unattended_ready) {
    notes.push("package_ready=false — swarm readiness not ready");
  } else {
    notes.push(
      "package_ready=true — entry+readiness intent only; live_execution_authorized=false",
    );
  }

  if (
    entry.live_execution_authorized !== false ||
    readiness.live_execution_authorized !== false
  ) {
    throw new Error("invariant: live_execution_authorized must remain false");
  }

  notes.push("live_execution_authorized=false");

  return {
    entry,
    readiness,
    package_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_entry_to_swarm_readiness_compose_advisory",
  };
}

export function formatMidnightOilEntryToSwarmReadinessSummary(
  c: MidnightOilEntryToSwarmReadinessCompose,
): string {
  return (
    `package_ready=${c.package_ready} · entry_ready=${c.entry.entry_ready} · ` +
    `goals=${c.entry.goal_count} · minutes=${c.entry.work_minutes} · ` +
    `live_execution_authorized=false`
  );
}
