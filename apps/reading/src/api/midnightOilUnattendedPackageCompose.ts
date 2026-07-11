/**
 * Midnight Oil unattended full package compose (pure).
 *
 * Operator vision: set time + goals + approve price ceiling; system packages
 * entry readiness + launch brief/readiness for unattended deep research —
 * without authorizing live workers.
 *
 * live_execution_authorized always false.
 */

import {
  composeMidnightOilEntryToSwarmReadiness,
  type MidnightOilEntryToSwarmReadinessCompose,
} from "./midnightOilEntryToSwarmReadinessCompose";
import type { MoGoalEntry } from "./midnightOilTimeGoalsPriceEntryCompose";
import {
  composeMidnightOilLaunchPackage,
  type MidnightOilLaunchPackage,
} from "./midnightOilLaunchPackageCompose";

export type { MoGoalEntry };

export interface MidnightOilUnattendedPackageInput {
  operator_id: string;
  work_minutes: number;
  goals: MoGoalEntry[];
  usd_per_hour?: number | null;
  approved_ceiling_usd?: number | null;
  operator_ack: boolean;
  unattended_ack: boolean;
  spend_consent: boolean;
  /**
   * When true, marks brief as dispatch-ready for entry readiness path.
   * Launch package builds its own brief from goals + approvals.
   */
  brief_dispatch_ready?: boolean;
}

export interface MidnightOilUnattendedPackageCompose {
  entry_readiness: MidnightOilEntryToSwarmReadinessCompose;
  launch: MidnightOilLaunchPackage;
  /**
   * True when entry_readiness.package_ready and launch.package_ready.
   * Still never authorizes live execution.
   */
  unattended_package_ready: boolean;
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_unattended_package_compose_advisory";
}

/**
 * Compose full unattended MO package: entry readiness + launch package.
 */
export function composeMidnightOilUnattendedPackage(
  input: MidnightOilUnattendedPackageInput,
): MidnightOilUnattendedPackageCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.unattended_ack !== "boolean") {
    throw new Error("unattended_ack must be an explicit boolean");
  }
  if (typeof input.spend_consent !== "boolean") {
    throw new Error("spend_consent must be an explicit boolean");
  }
  if (!Array.isArray(input.goals) || input.goals.length === 0) {
    throw new Error("goals must be a non-empty array");
  }

  const notes: string[] = [
    "live_execution_authorized=false — unattended package never launches workers",
  ];

  // Entry readiness: treat operator_ack as brief ready when entry is approved
  const brief_dispatch_ready =
    input.brief_dispatch_ready === undefined
      ? input.operator_ack && input.unattended_ack
      : input.brief_dispatch_ready;
  if (typeof brief_dispatch_ready !== "boolean") {
    throw new Error("brief_dispatch_ready must be boolean when set");
  }

  const entry_readiness = composeMidnightOilEntryToSwarmReadiness({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goals: input.goals,
    usd_per_hour: input.usd_per_hour,
    approved_ceiling_usd: input.approved_ceiling_usd,
    operator_ack: input.operator_ack,
    brief_dispatch_ready,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
  });
  notes.push(...entry_readiness.notes);

  // Map MoGoalEntry (title) → SwarmGoal (statement)
  const swarmGoals = input.goals.map((g, i) => ({
    goal_id: g.goal_id,
    statement: g.title,
    priority: input.goals.length - i,
  }));

  const launch = composeMidnightOilLaunchPackage({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goals: swarmGoals,
    price_ceiling_usd:
      entry_readiness.entry.approved_ceiling_usd ??
      input.approved_ceiling_usd ??
      null,
    recommended_ceiling_usd:
      entry_readiness.entry.recommend.recommended_ceiling_usd,
    usd_per_hour: input.usd_per_hour,
    operator_approved: input.operator_ack,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
  });
  notes.push(...launch.notes);

  const unattended_package_ready =
    entry_readiness.package_ready &&
    launch.package_ready &&
    entry_readiness.live_execution_authorized === false &&
    launch.live_execution_authorized === false;

  if (!entry_readiness.package_ready) {
    notes.push("unattended_package_ready=false — entry readiness not ready");
  } else if (!launch.package_ready) {
    notes.push("unattended_package_ready=false — launch package not ready");
  } else {
    notes.push(
      "unattended_package_ready=true — full unattended intent; still live_execution_authorized=false",
    );
  }

  if (
    entry_readiness.live_execution_authorized !== false ||
    launch.live_execution_authorized !== false
  ) {
    throw new Error("invariant: live_execution_authorized must remain false");
  }

  notes.push("live_execution_authorized=false");

  return {
    entry_readiness,
    launch,
    unattended_package_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_unattended_package_compose_advisory",
  };
}

export function formatMidnightOilUnattendedPackageSummary(
  c: MidnightOilUnattendedPackageCompose,
): string {
  return (
    `unattended_package_ready=${c.unattended_package_ready} · ` +
    `entry_ready=${c.entry_readiness.entry.entry_ready} · ` +
    `launch_ready=${c.launch.package_ready} · ` +
    `goals=${c.entry_readiness.entry.goal_count} · ` +
    `live_execution_authorized=false`
  );
}

