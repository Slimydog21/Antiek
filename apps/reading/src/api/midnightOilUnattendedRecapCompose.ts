/**
 * Midnight Oil unattended recap compose (pure).
 *
 * Operator vision: set time + goals + price ceiling; swarm works unattended;
 * operator returns to a recap of progress, spend vs ceiling, and artifacts.
 *
 * This pure layer never re-launches workers.
 * live_execution_authorized always false.
 * store_mutated always false.
 */

export interface MidnightOilRecapGoal {
  goal_id: string;
  title: string;
  /** Caller-supplied status — never invented. */
  status: "pending" | "in_progress" | "done" | "blocked" | "skipped";
  /** Optional notes from run (caller-supplied). */
  notes?: string;
}

export interface MidnightOilUnattendedRecapInput {
  run_id: string;
  operator_id: string;
  work_minutes_planned: number;
  /** Actual minutes worked if known; null = unknown honesty. */
  work_minutes_actual: number | null;
  goals: MidnightOilRecapGoal[];
  /** Operator-approved ceiling for this run; null = unknown. */
  price_ceiling_usd: number | null;
  /** Settled or reported spend; null = unknown. */
  spend_usd: number | null;
  /** Caller-supplied artifact ids/paths only. */
  artifact_ids?: string[] | null;
  operator_ack: boolean;
}

export interface MidnightOilUnattendedRecapCompose {
  run_id: string;
  operator_id: string;
  goal_count: number;
  goals_done: number;
  goals_blocked: number;
  goals_pending: number;
  /** True when spend known and ceiling known and spend <= ceiling. */
  within_ceiling: boolean | null;
  /** True when ≥1 goal done or artifact present and operator_ack. */
  recap_ready: boolean;
  artifact_count: number;
  /** Always false — recap never re-authorizes live MO workers. */
  live_execution_authorized: false;
  /** Always false — pure recap does not persist. */
  store_mutated: false;
  notes: string[];
  authority: "midnight_oil_unattended_recap_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireNonNegFinite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative finite number`);
  }
  return value;
}

const VALID_STATUS = new Set([
  "pending",
  "in_progress",
  "done",
  "blocked",
  "skipped",
]);

/**
 * Compose an unattended MO run recap for the operator.
 * Never live-executes; never invents spend or goal outcomes.
 */
export function composeMidnightOilUnattendedRecap(
  input: MidnightOilUnattendedRecapInput,
): MidnightOilUnattendedRecapCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const run_id = requireNonEmpty(input.run_id, "run_id");
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  const work_minutes_planned = requireNonNegFinite(
    input.work_minutes_planned,
    "work_minutes_planned",
  );
  if (work_minutes_planned <= 0) {
    throw new Error("work_minutes_planned must be > 0");
  }
  if (
    input.work_minutes_actual !== null &&
    input.work_minutes_actual !== undefined &&
    (typeof input.work_minutes_actual !== "number" ||
      !Number.isFinite(input.work_minutes_actual) ||
      input.work_minutes_actual < 0)
  ) {
    throw new Error(
      "work_minutes_actual must be non-negative finite number or null",
    );
  }
  const work_minutes_actual =
    input.work_minutes_actual === undefined ? null : input.work_minutes_actual;

  if (!Array.isArray(input.goals) || input.goals.length === 0) {
    throw new Error("goals must be a non-empty array");
  }

  const notes: string[] = [
    "live_execution_authorized=false — recap never re-launches MO workers",
    "store_mutated=false — recap is advisory snapshot only",
    "goal statuses and spend are caller-supplied only (no invent)",
  ];

  let goals_done = 0;
  let goals_blocked = 0;
  let goals_pending = 0;
  const seen = new Set<string>();

  for (let i = 0; i < input.goals.length; i++) {
    const g = input.goals[i];
    if (!g || typeof g !== "object") {
      throw new Error(`goals[${i}] must be an object`);
    }
    const id = requireNonEmpty(g.goal_id, `goals[${i}].goal_id`);
    if (seen.has(id)) {
      throw new Error(`duplicate goal_id: ${id}`);
    }
    seen.add(id);
    requireNonEmpty(g.title, `goals[${i}].title`);
    if (!VALID_STATUS.has(g.status)) {
      throw new Error(
        `goals[${i}].status must be pending|in_progress|done|blocked|skipped`,
      );
    }
    if (g.notes != null) {
      requireNonEmpty(g.notes, `goals[${i}].notes`);
    }
    if (g.status === "done") goals_done += 1;
    else if (g.status === "blocked") goals_blocked += 1;
    else if (g.status === "pending" || g.status === "in_progress") {
      goals_pending += 1;
    }
  }

  const goal_count = input.goals.length;
  notes.push(
    `goals=${goal_count} · done=${goals_done} · blocked=${goals_blocked} · pendingish=${goals_pending}`,
  );
  notes.push(`work_minutes_planned=${work_minutes_planned}`);
  if (work_minutes_actual === null) {
    notes.push("work_minutes_actual=null (unknown honesty)");
  } else {
    notes.push(`work_minutes_actual=${work_minutes_actual}`);
  }

  let within_ceiling: boolean | null = null;
  if (
    input.price_ceiling_usd !== null &&
    input.price_ceiling_usd !== undefined &&
    input.spend_usd !== null &&
    input.spend_usd !== undefined
  ) {
    if (
      typeof input.price_ceiling_usd !== "number" ||
      !Number.isFinite(input.price_ceiling_usd) ||
      input.price_ceiling_usd < 0
    ) {
      throw new Error("price_ceiling_usd must be non-negative finite when set");
    }
    if (
      typeof input.spend_usd !== "number" ||
      !Number.isFinite(input.spend_usd) ||
      input.spend_usd < 0
    ) {
      throw new Error("spend_usd must be non-negative finite when set");
    }
    within_ceiling = input.spend_usd <= input.price_ceiling_usd;
    notes.push(
      within_ceiling
        ? `within_ceiling=true · spend=${input.spend_usd} ≤ ceiling=${input.price_ceiling_usd}`
        : `within_ceiling=false · spend=${input.spend_usd} > ceiling=${input.price_ceiling_usd}`,
    );
  } else {
    notes.push(
      "within_ceiling=null — spend and/or ceiling unknown (no invent $0)",
    );
  }

  let artifact_count = 0;
  if (input.artifact_ids != null) {
    if (!Array.isArray(input.artifact_ids)) {
      throw new Error("artifact_ids must be an array when set");
    }
    const aseen = new Set<string>();
    for (let i = 0; i < input.artifact_ids.length; i++) {
      const aid = requireNonEmpty(
        input.artifact_ids[i],
        `artifact_ids[${i}]`,
      );
      if (aseen.has(aid)) {
        throw new Error(`duplicate artifact_id: ${aid}`);
      }
      aseen.add(aid);
    }
    artifact_count = aseen.size;
    notes.push(`artifact_count=${artifact_count}`);
  }

  const hasProgress = goals_done >= 1 || artifact_count >= 1;
  const recap_ready = input.operator_ack && hasProgress;
  if (!input.operator_ack) {
    notes.push("recap_ready=false — operator_ack required");
  } else if (!hasProgress) {
    notes.push(
      "recap_ready=false — no done goals or artifacts (no invent progress)",
    );
  } else {
    notes.push("recap_ready=true — operator may review unattended outcomes");
  }

  notes.push("live_execution_authorized=false");
  notes.push("store_mutated=false");

  return {
    run_id,
    operator_id,
    goal_count,
    goals_done,
    goals_blocked,
    goals_pending,
    within_ceiling,
    recap_ready,
    artifact_count,
    live_execution_authorized: false,
    store_mutated: false,
    notes,
    authority: "midnight_oil_unattended_recap_compose_advisory",
  };
}

export function formatMidnightOilUnattendedRecapSummary(
  c: MidnightOilUnattendedRecapCompose,
): string {
  return (
    `recap_ready=${c.recap_ready} · done=${c.goals_done}/${c.goal_count} · ` +
    `within_ceiling=${c.within_ceiling} · artifacts=${c.artifact_count} · ` +
    `live_execution_authorized=false`
  );
}
