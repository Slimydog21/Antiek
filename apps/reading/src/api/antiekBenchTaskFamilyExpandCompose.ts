/**
 * Antiek-bench task-family expand compose (pure).
 *
 * Operator vision: recursive Antiek-bench that grows sub-benchmarks as the
 * platform expands — differentiating tasks from usage patterns + proposed
 * new families (never invented).
 *
 * backlog_mutated always false.
 * store_mutated always false.
 * suite_rewritten always false.
 */

import {
  composeAntiekBenchWeeklyUsageLearn,
  type AntiekBenchWeeklyUsageLearnCompose,
  type WeeklyUsageEvent,
} from "./antiekBenchWeeklyUsageLearnCompose";

export interface TaskFamilySeed {
  task: string;
  /** Optional description — caller-supplied only. */
  description?: string | null;
}

export interface AntiekBenchTaskFamilyExpandInput {
  week_id: string;
  /** Existing task families already in the bench suite (caller-supplied). */
  existing_tasks: string[];
  /** Proposed new task families as platform expands (caller-supplied). */
  proposed_new_tasks?: TaskFamilySeed[] | null;
  /** Weekly usage events for learn proposals. */
  events: WeeklyUsageEvent[];
  operator_ack: boolean;
  min_events_per_task?: number;
}

export interface TaskFamilyExpandItem {
  task: string;
  source: "existing" | "proposed_new" | "usage_learn";
  /** True when this family should be emphasized in next rewrite (intent). */
  expand_recommended: boolean;
  reason: string;
}

export interface AntiekBenchTaskFamilyExpandCompose {
  week_id: string;
  learn: AntiekBenchWeeklyUsageLearnCompose;
  families: TaskFamilyExpandItem[];
  family_count: number;
  new_proposed_count: number;
  expand_recommended_count: number;
  /**
   * True when operator_ack and (≥1 expand recommendation or ≥1 new proposed).
   */
  expand_ready: boolean;
  backlog_mutated: false;
  store_mutated: false;
  suite_rewritten: false;
  notes: string[];
  authority: "antiek_bench_task_family_expand_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose task-family expansion recommendations for Antiek-bench.
 * Never mutates bench store or rewrites suite.
 */
export function composeAntiekBenchTaskFamilyExpand(
  input: AntiekBenchTaskFamilyExpandInput,
): AntiekBenchTaskFamilyExpandCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const week_id = requireNonEmpty(input.week_id, "week_id");
  if (!Array.isArray(input.existing_tasks)) {
    throw new Error("existing_tasks must be an array");
  }

  const notes: string[] = [
    "backlog_mutated=false — no bench backlog write",
    "store_mutated=false — no bench store write",
    "suite_rewritten=false — rewrite is intent only",
  ];

  const existing: string[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < input.existing_tasks.length; i++) {
    const t = requireNonEmpty(
      input.existing_tasks[i],
      `existing_tasks[${i}]`,
    );
    if (seen.has(t)) {
      throw new Error(`duplicate existing_tasks: ${t}`);
    }
    seen.add(t);
    existing.push(t);
  }

  const proposed: TaskFamilySeed[] = [];
  if (input.proposed_new_tasks != null) {
    if (!Array.isArray(input.proposed_new_tasks)) {
      throw new Error("proposed_new_tasks must be an array when set");
    }
    for (let i = 0; i < input.proposed_new_tasks.length; i++) {
      const p = input.proposed_new_tasks[i];
      if (!p || typeof p !== "object") {
        throw new Error(`proposed_new_tasks[${i}] must be an object`);
      }
      const task = requireNonEmpty(
        p.task,
        `proposed_new_tasks[${i}].task`,
      );
      if (seen.has(task)) {
        notes.push(
          `proposed_new_tasks[${i}] ${task} already exists — treat as usage expand only`,
        );
      }
      proposed.push({
        task,
        description:
          p.description == null || p.description === undefined
            ? null
            : requireNonEmpty(
                p.description,
                `proposed_new_tasks[${i}].description`,
              ),
      });
    }
  }

  const learn = composeAntiekBenchWeeklyUsageLearn({
    week_id,
    events: input.events,
    operator_ack: input.operator_ack,
    min_events_per_task: input.min_events_per_task,
  });
  notes.push(...learn.notes);

  const learnExpand = new Map<string, string>();
  for (const prop of learn.proposals) {
    if (
      prop.emphasis === "expand_failure_cases" ||
      prop.emphasis === "expand_success_cases"
    ) {
      learnExpand.set(prop.task, prop.reason);
    }
  }

  const families: TaskFamilyExpandItem[] = [];

  for (const t of existing) {
    const reason = learnExpand.get(t);
    families.push({
      task: t,
      source: "existing",
      expand_recommended: reason != null,
      reason: reason ?? "hold_stable — no expand signal from weekly learn",
    });
  }

  let new_proposed_count = 0;
  for (const p of proposed) {
    if (existing.includes(p.task)) {
      // already noted; ensure expand flag from learn if any
      continue;
    }
    new_proposed_count += 1;
    const learnReason = learnExpand.get(p.task);
    families.push({
      task: p.task,
      source: "proposed_new",
      expand_recommended: true,
      reason:
        learnReason ??
        (p.description
          ? `platform expansion: ${p.description}`
          : "platform expansion — new task family proposed (caller-supplied)"),
    });
  }

  // usage-only tasks not in existing/proposed
  for (const [task, reason] of learnExpand) {
    if (families.some((f) => f.task === task)) continue;
    families.push({
      task,
      source: "usage_learn",
      expand_recommended: true,
      reason,
    });
  }

  const expand_recommended_count = families.filter(
    (f) => f.expand_recommended,
  ).length;
  notes.push(
    `family_count=${families.length} · new_proposed=${new_proposed_count} · expand_recommended=${expand_recommended_count}`,
  );

  const expand_ready =
    input.operator_ack &&
    (expand_recommended_count > 0 || new_proposed_count > 0);
  if (!input.operator_ack) {
    notes.push("expand_ready=false — operator_ack required");
  } else if (!expand_ready) {
    notes.push(
      "expand_ready=false — no expand recommendations or new families",
    );
  } else {
    notes.push(
      "expand_ready=true — expansion intent only; suite_rewritten=false",
    );
  }

  if (
    learn.backlog_mutated !== false ||
    learn.store_mutated !== false
  ) {
    throw new Error("invariant: learn honesty flags must remain false");
  }

  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("suite_rewritten=false");

  return {
    week_id,
    learn,
    families,
    family_count: families.length,
    new_proposed_count,
    expand_recommended_count,
    expand_ready,
    backlog_mutated: false,
    store_mutated: false,
    suite_rewritten: false,
    notes,
    authority: "antiek_bench_task_family_expand_compose_advisory",
  };
}

export function formatAntiekBenchTaskFamilyExpandSummary(
  c: AntiekBenchTaskFamilyExpandCompose,
): string {
  return (
    `expand_ready=${c.expand_ready} · families=${c.family_count} · ` +
    `new=${c.new_proposed_count} · expand_rec=${c.expand_recommended_count} · ` +
    `backlog_mutated=false · store_mutated=false · suite_rewritten=false`
  );
}
