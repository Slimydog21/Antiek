/**
 * Midnight Oil swarm brief (pure client).
 *
 * Operator vision: set a work window + goals; system recommends a price
 * ceiling; swarm plan is produced for unattended multi-agent deep research.
 *
 * live_execution_authorized is always false in this pure layer.
 * price_ceiling is advisory only — never charges.
 */

export interface SwarmGoal {
  goal_id: string;
  statement: string;
  priority: number;
}

export interface MidnightOilSwarmBriefInput {
  operator_id: string;
  /** Work window in minutes (positive finite). */
  work_minutes: number;
  goals: SwarmGoal[];
  /**
   * Operator-approved price ceiling USD. Null means unknown/not set —
   * brief still builds but dispatch_ready stays false.
   */
  price_ceiling_usd: number | null;
  /** Recommended ceiling from price-ceiling recommender (advisory). */
  recommended_ceiling_usd?: number | null;
  operator_approved: boolean;
}

export interface SwarmLane {
  lane_id: string;
  goal_id: string;
  statement: string;
  /** Fractional share of work window (sums ~1). */
  time_share: number;
}

export interface MidnightOilSwarmBrief {
  operator_id: string;
  work_minutes: number;
  goals: SwarmGoal[];
  lanes: SwarmLane[];
  price_ceiling_usd: number | null;
  recommended_ceiling_usd: number | null;
  operator_approved: boolean;
  /** True only when operator_approved and finite positive ceiling. */
  dispatch_ready: boolean;
  /** Always false — pure brief never authorizes live execution. */
  live_execution_authorized: false;
  notes: string[];
  authority: "midnight_oil_swarm_brief_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireFiniteMoney(value: unknown, name: string): number | null {
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
 * Build an unattended swarm brief from time + goals + optional ceiling.
 * Never authorizes live execution.
 */
export function buildMidnightOilSwarmBrief(
  input: MidnightOilSwarmBriefInput,
): MidnightOilSwarmBrief {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_approved !== "boolean") {
    throw new Error("operator_approved must be an explicit boolean");
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  if (
    typeof input.work_minutes !== "number" ||
    !Number.isFinite(input.work_minutes) ||
    input.work_minutes <= 0
  ) {
    throw new Error("work_minutes must be a positive finite number");
  }
  if (!Array.isArray(input.goals) || input.goals.length === 0) {
    throw new Error("goals must be a non-empty array");
  }

  const notes: string[] = [];
  const goals: SwarmGoal[] = [];
  let prioritySum = 0;
  for (let i = 0; i < input.goals.length; i++) {
    const g = input.goals[i];
    if (!g || typeof g !== "object") {
      throw new Error(`goals[${i}] must be an object`);
    }
    const goal_id = requireNonEmpty(g.goal_id, `goals[${i}].goal_id`);
    const statement = requireNonEmpty(g.statement, `goals[${i}].statement`);
    if (typeof g.priority !== "number" || !Number.isFinite(g.priority) || g.priority <= 0) {
      throw new Error(`goals[${i}].priority must be a positive finite number`);
    }
    goals.push({ goal_id, statement, priority: g.priority });
    prioritySum += g.priority;
  }
  if (!Number.isFinite(prioritySum) || prioritySum <= 0) {
    throw new Error("priority sum overflowed or non-positive");
  }

  const price_ceiling_usd = requireFiniteMoney(
    input.price_ceiling_usd,
    "price_ceiling_usd",
  );
  const recommended_ceiling_usd = requireFiniteMoney(
    input.recommended_ceiling_usd ?? null,
    "recommended_ceiling_usd",
  );

  const lanes: SwarmLane[] = goals.map((g, i) => ({
    lane_id: `lane_${i}_${g.goal_id}`,
    goal_id: g.goal_id,
    statement: g.statement,
    time_share: g.priority / prioritySum,
  }));

  let dispatch_ready = false;
  if (!input.operator_approved) {
    notes.push("operator_approved=false — dispatch_ready=false");
  } else if (price_ceiling_usd === null) {
    notes.push("price_ceiling_usd unknown — dispatch_ready=false (no invent 0)");
  } else if (price_ceiling_usd === 0) {
    notes.push(
      "price_ceiling_usd=0 — dispatch_ready=true for zero-spend dry plan only",
    );
    dispatch_ready = true;
  } else {
    dispatch_ready = true;
    notes.push("operator approved with positive ceiling — dispatch_ready=true");
  }

  if (
    recommended_ceiling_usd !== null &&
    price_ceiling_usd !== null &&
    price_ceiling_usd > recommended_ceiling_usd
  ) {
    notes.push(
      `operator ceiling $${price_ceiling_usd} exceeds recommended $${recommended_ceiling_usd} (advisory only)`,
    );
  }

  notes.push("live_execution_authorized=false");
  notes.push("pure swarm brief — no worker dispatch, no spend");

  return {
    operator_id,
    work_minutes: input.work_minutes,
    goals,
    lanes,
    price_ceiling_usd,
    recommended_ceiling_usd,
    operator_approved: input.operator_approved,
    dispatch_ready,
    live_execution_authorized: false,
    notes,
    authority: "midnight_oil_swarm_brief_advisory",
  };
}

export function formatSwarmBriefSummary(b: MidnightOilSwarmBrief): string {
  return (
    `lanes=${b.lanes.length} · minutes=${b.work_minutes} · ` +
    `dispatch_ready=${b.dispatch_ready} · live_execution_authorized=false`
  );
}
