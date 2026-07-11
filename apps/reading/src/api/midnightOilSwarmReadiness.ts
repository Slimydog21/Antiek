/**
 * Midnight Oil swarm readiness (pure client).
 *
 * Operator vision: unattended deep research after time + goals + price
 * ceiling approval. This pure layer decides whether a swarm brief is ready
 * for *advisory* unattended handoff — never authorizes live workers.
 *
 * live_execution_authorized is always false.
 */

export interface MidnightOilSwarmReadinessInput {
  operator_id: string;
  /** Minutes of work window (positive). */
  work_minutes: number;
  /** Number of goals in the swarm brief (>=1). */
  goal_count: number;
  /** Operator-approved price ceiling USD; null = unknown. */
  price_ceiling_usd: number | null;
  /** Recommended ceiling (advisory). */
  recommended_ceiling_usd?: number | null;
  /** From swarm brief: operator approved the plan. */
  brief_dispatch_ready: boolean;
  /** Explicit operator ack for unattended handoff. */
  unattended_ack: boolean;
  /**
   * Spend consent receipt present (from spend consent view).
   * Required when ceiling > 0.
   */
  spend_consent: boolean;
}

export interface MidnightOilSwarmReadinessDecision {
  operator_id: string;
  goals_ready: boolean;
  time_ready: boolean;
  ceiling_ready: boolean;
  consent_ready: boolean;
  brief_ready: boolean;
  /** True when all readiness gates pass (advisory unattended handoff). */
  unattended_ready: boolean;
  /** Always false — pure layer never authorizes live MO workers. */
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_swarm_readiness_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
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
 * Evaluate whether a Midnight Oil swarm is ready for unattended handoff.
 * Never authorizes live execution.
 */
export function evaluateMidnightOilSwarmReadiness(
  input: MidnightOilSwarmReadinessInput,
): MidnightOilSwarmReadinessDecision {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  if (
    typeof input.work_minutes !== "number" ||
    !Number.isFinite(input.work_minutes) ||
    input.work_minutes <= 0
  ) {
    throw new Error("work_minutes must be a positive finite number");
  }
  if (
    typeof input.goal_count !== "number" ||
    !Number.isInteger(input.goal_count) ||
    input.goal_count < 0
  ) {
    throw new Error("goal_count must be a non-negative integer");
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

  const price_ceiling_usd = finiteMoney(
    input.price_ceiling_usd,
    "price_ceiling_usd",
  );
  const recommended_ceiling_usd = finiteMoney(
    input.recommended_ceiling_usd ?? null,
    "recommended_ceiling_usd",
  );

  const notes: string[] = [
    "live_execution_authorized=false — pure unattended readiness only",
  ];

  const goals_ready = input.goal_count >= 1;
  if (!goals_ready) {
    notes.push("goal_count < 1 — goals_ready=false");
  } else {
    notes.push(`goals_ready=true (count=${input.goal_count})`);
  }

  const time_ready = input.work_minutes > 0;
  notes.push(
    time_ready
      ? `time_ready=true (minutes=${input.work_minutes})`
      : "time_ready=false",
  );

  let ceiling_ready = false;
  if (price_ceiling_usd === null) {
    notes.push(
      "price_ceiling_usd unknown — ceiling_ready=false (no invent 0)",
    );
    ceiling_ready = false;
  } else {
    ceiling_ready = true;
    notes.push(`ceiling_ready=true (ceiling=${price_ceiling_usd})`);
    if (
      recommended_ceiling_usd !== null &&
      price_ceiling_usd > recommended_ceiling_usd
    ) {
      notes.push(
        `operator ceiling ${price_ceiling_usd} exceeds recommended ${recommended_ceiling_usd} (advisory)`,
      );
    }
  }

  let consent_ready = false;
  if (price_ceiling_usd === null) {
    consent_ready = false;
    notes.push("consent_ready=false (ceiling unknown)");
  } else if (price_ceiling_usd === 0) {
    // Zero-spend dry plan: consent optional
    consent_ready = true;
    notes.push(
      "price_ceiling_usd=0 — consent_ready=true (zero-spend dry; consent optional)",
    );
  } else if (input.spend_consent) {
    consent_ready = true;
    notes.push("spend_consent=true — consent_ready=true");
  } else {
    consent_ready = false;
    notes.push(
      "price_ceiling_usd>0 without spend_consent — consent_ready=false",
    );
  }

  const brief_ready = input.brief_dispatch_ready === true;
  if (!brief_ready) {
    notes.push("brief_dispatch_ready=false — brief_ready=false");
  } else {
    notes.push("brief_dispatch_ready=true — brief_ready=true");
  }

  if (!input.unattended_ack) {
    notes.push("unattended_ack=false — blocks unattended_ready");
  }

  const unattended_ready =
    goals_ready &&
    time_ready &&
    ceiling_ready &&
    consent_ready &&
    brief_ready &&
    input.unattended_ack === true;

  notes.push(`unattended_ready=${unattended_ready}`);
  notes.push("live_execution_authorized=false");

  return {
    operator_id,
    goals_ready,
    time_ready,
    ceiling_ready,
    consent_ready,
    brief_ready,
    unattended_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_swarm_readiness_advisory",
  };
}

export function formatSwarmReadinessSummary(
  d: MidnightOilSwarmReadinessDecision,
): string {
  return (
    `operator=${d.operator_id} · unattended_ready=${d.unattended_ready} · ` +
    `live_execution_authorized=false`
  );
}
