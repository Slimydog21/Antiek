/**
 * Midnight Oil full launch package compose (pure).
 *
 * Operator vision: set time of work + goals; system recommends a price
 * ceiling to approve; then unattended swarm can hand off. This pure layer
 * composes recommended ceiling + swarm brief + readiness into one package.
 *
 * live_execution_authorized is always false — never dispatches workers.
 */

import {
  buildMidnightOilSwarmBrief,
  type MidnightOilSwarmBrief,
  type SwarmGoal,
} from "./midnightOilSwarmBrief";
import {
  evaluateMidnightOilSwarmReadiness,
  type MidnightOilSwarmReadinessDecision,
} from "./midnightOilSwarmReadiness";

export interface MidnightOilPriceCeilingRecommendInput {
  /** Work window minutes (positive finite). */
  work_minutes: number;
  /** Goal count (>=1). */
  goal_count: number;
  /**
   * Optional blended USD per hour of unattended work.
   * Null/undefined = unknown — recommended stays null (no invent $0).
   */
  usd_per_hour?: number | null;
  /** Optional per-goal multiplier (default 1 when rate known). */
  goal_intensity?: number | null;
}

export interface MidnightOilPriceCeilingRecommend {
  recommended_ceiling_usd: number | null;
  work_hours: number | null;
  notes: string[];
  authority: "midnight_oil_price_ceiling_recommend_advisory";
}

export interface MidnightOilLaunchPackageInput {
  operator_id: string;
  work_minutes: number;
  goals: SwarmGoal[];
  /** Operator-approved ceiling; null = unknown. */
  price_ceiling_usd: number | null;
  /**
   * Optional override of recommended ceiling. When omitted, package computes
   * recommend from usd_per_hour (or leaves null).
   */
  recommended_ceiling_usd?: number | null;
  usd_per_hour?: number | null;
  operator_approved: boolean;
  unattended_ack: boolean;
  spend_consent: boolean;
}

export interface MidnightOilLaunchPackage {
  operator_id: string;
  recommend: MidnightOilPriceCeilingRecommend;
  brief: MidnightOilSwarmBrief;
  readiness: MidnightOilSwarmReadinessDecision;
  /**
   * True when brief.dispatch_ready and readiness.unattended_ready.
   * Still does not authorize live workers.
   */
  package_ready: boolean;
  /** Always false — pure package never launches MO workers. */
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_launch_package_compose_advisory";
}

function requirePositiveFinite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive finite number`);
  }
  return value;
}

function requireNonNegInt(value: unknown, name: string): number {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < 0
  ) {
    throw new Error(`${name} must be a non-negative integer`);
  }
  return value;
}

function finiteMoney(value: unknown, name: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be finite number or null`);
  }
  if (value < 0) {
    throw new Error(`${name} must be >= 0`);
  }
  return value;
}

/**
 * Recommend a price ceiling from work window + goals + optional hourly rate.
 * Never invents a $0 recommendation when rates are unknown.
 */
export function recommendMidnightOilPriceCeiling(
  input: MidnightOilPriceCeilingRecommendInput,
): MidnightOilPriceCeilingRecommend {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const work_minutes = requirePositiveFinite(
    input.work_minutes,
    "work_minutes",
  );
  const goal_count = requireNonNegInt(input.goal_count, "goal_count");
  if (goal_count < 1) {
    throw new Error("goal_count must be >= 1 for a recommendation");
  }

  const notes: string[] = [
    "recommended ceiling is advisory only — never charges",
  ];
  const work_hours = work_minutes / 60;
  if (!Number.isFinite(work_hours)) {
    throw new Error("work_hours overflowed to non-finite");
  }

  const usd_per_hour = finiteMoney(input.usd_per_hour ?? null, "usd_per_hour");
  let intensity = 1;
  if (input.goal_intensity !== undefined && input.goal_intensity !== null) {
    intensity = requirePositiveFinite(input.goal_intensity, "goal_intensity");
  }

  if (usd_per_hour === null) {
    notes.push(
      "usd_per_hour unknown — recommended_ceiling_usd=null (no invent 0)",
    );
    return {
      recommended_ceiling_usd: null,
      work_hours,
      notes,
      authority: "midnight_oil_price_ceiling_recommend_advisory",
    };
  }

  // Scale hours by goal intensity and mild multi-goal fan-out (sqrt to avoid
  // linear explosion). Pure advisory arithmetic only.
  const fanout = Math.sqrt(goal_count);
  if (!Number.isFinite(fanout) || fanout <= 0) {
    throw new Error("goal fanout overflowed");
  }
  const recommended = usd_per_hour * work_hours * intensity * fanout;
  if (!Number.isFinite(recommended)) {
    throw new Error("recommended_ceiling_usd overflowed to non-finite");
  }
  // Round to cents for operator display honesty.
  const recommended_ceiling_usd = Math.round(recommended * 100) / 100;
  notes.push(
    `recommended=$${recommended_ceiling_usd} from rate=$${usd_per_hour}/h · ` +
      `hours=${work_hours} · goals=${goal_count} · intensity=${intensity}`,
  );

  return {
    recommended_ceiling_usd,
    work_hours,
    notes,
    authority: "midnight_oil_price_ceiling_recommend_advisory",
  };
}

/**
 * Compose full MO launch package: recommend + brief + readiness.
 * Never authorizes live execution.
 */
export function composeMidnightOilLaunchPackage(
  input: MidnightOilLaunchPackageInput,
): MidnightOilLaunchPackage {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_approved !== "boolean") {
    throw new Error("operator_approved must be an explicit boolean");
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
    "live_execution_authorized=false — launch package advisory only",
  ];

  let recommend: MidnightOilPriceCeilingRecommend;
  if (
    input.recommended_ceiling_usd !== undefined &&
    input.recommended_ceiling_usd !== null
  ) {
    const forced = finiteMoney(
      input.recommended_ceiling_usd,
      "recommended_ceiling_usd",
    );
    recommend = {
      recommended_ceiling_usd: forced,
      work_hours: null,
      notes: [
        "recommended_ceiling_usd caller-supplied override (not recomputed)",
      ],
      authority: "midnight_oil_price_ceiling_recommend_advisory",
    };
  } else if (
    input.recommended_ceiling_usd === null &&
    input.usd_per_hour === undefined
  ) {
    // Explicit null recommended with no rate — honesty path
    recommend = {
      recommended_ceiling_usd: null,
      work_hours: null,
      notes: [
        "recommended_ceiling_usd explicitly null — no invent",
      ],
      authority: "midnight_oil_price_ceiling_recommend_advisory",
    };
  } else {
    recommend = recommendMidnightOilPriceCeiling({
      work_minutes: input.work_minutes,
      goal_count: input.goals.length,
      usd_per_hour: input.usd_per_hour ?? null,
    });
  }

  const brief = buildMidnightOilSwarmBrief({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goals: input.goals,
    price_ceiling_usd: input.price_ceiling_usd,
    recommended_ceiling_usd: recommend.recommended_ceiling_usd,
    operator_approved: input.operator_approved,
  });

  const readiness = evaluateMidnightOilSwarmReadiness({
    operator_id: input.operator_id,
    work_minutes: input.work_minutes,
    goal_count: input.goals.length,
    price_ceiling_usd: input.price_ceiling_usd,
    recommended_ceiling_usd: recommend.recommended_ceiling_usd,
    brief_dispatch_ready: brief.dispatch_ready,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
  });

  const package_ready =
    brief.dispatch_ready === true && readiness.unattended_ready === true;

  if (package_ready) {
    notes.push(
      "package_ready=true — brief dispatch_ready + unattended_ready (still no live exec)",
    );
  } else {
    notes.push(
      `package_ready=false (dispatch_ready=${brief.dispatch_ready}, ` +
        `unattended_ready=${readiness.unattended_ready})`,
    );
  }
  notes.push("live_execution_authorized=false");

  return {
    operator_id: brief.operator_id,
    recommend,
    brief,
    readiness,
    package_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_launch_package_compose_advisory",
  };
}

export function formatMidnightOilLaunchPackageSummary(
  p: MidnightOilLaunchPackage,
): string {
  return (
    `MO package · ready=${p.package_ready} · ` +
    `recommended=${p.recommend.recommended_ceiling_usd ?? "null"} · ` +
    `live_execution_authorized=false`
  );
}
