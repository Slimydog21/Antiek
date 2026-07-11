/**
 * Antiek-bench weekly usage-learn compose (pure).
 *
 * Operator vision: recursive benchmark that learns from usage patterns —
 * what worked / didn't in a week — to re-write the benchmark and
 * differentiating sub-benchmarks as the platform expands.
 *
 * This pure layer proposes rewrite recommendations only.
 * backlog_mutated always false.
 * store_mutated always false.
 * Never invents usage events.
 */

export type UsageOutcome = "worked" | "failed" | "mixed" | "unknown";

export interface WeeklyUsageEvent {
  event_id: string;
  /** Task family (deep_research, twin_notes, etc.). */
  task: string;
  model_id: string;
  outcome: UsageOutcome;
  /** Optional quality score 0..1. */
  score?: number | null;
}

export interface SubBenchmarkRewriteProposal {
  task: string;
  /** Why rewrite is proposed — derived from counts, not invented prose. */
  reason: string;
  /** Suggested emphasis: more cases for failures, keep stable for wins. */
  emphasis: "expand_failure_cases" | "expand_success_cases" | "hold_stable";
  event_count: number;
  failed_count: number;
  worked_count: number;
}

export interface AntiekBenchWeeklyUsageLearnInput {
  week_id: string;
  events: WeeklyUsageEvent[];
  operator_ack: boolean;
  /**
   * Minimum events per task before proposing a rewrite.
   * Default 3 when omitted.
   */
  min_events_per_task?: number;
}

export interface AntiekBenchWeeklyUsageLearnCompose {
  week_id: string;
  event_count: number;
  task_count: number;
  proposals: SubBenchmarkRewriteProposal[];
  proposal_count: number;
  /** True when ≥1 proposal and operator_ack. */
  learn_ready: boolean;
  /** Always false — pure layer never mutates bench backlog. */
  backlog_mutated: false;
  /** Always false — pure layer never writes bench store. */
  store_mutated: false;
  notes: string[];
  authority: "antiek_bench_weekly_usage_learn_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

const VALID_OUTCOME = new Set<UsageOutcome>([
  "worked",
  "failed",
  "mixed",
  "unknown",
]);

/**
 * Propose Antiek-bench sub-benchmark rewrites from weekly usage events.
 * Never invents events; never mutates bench store/backlog.
 */
export function composeAntiekBenchWeeklyUsageLearn(
  input: AntiekBenchWeeklyUsageLearnInput,
): AntiekBenchWeeklyUsageLearnCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const week_id = requireNonEmpty(input.week_id, "week_id");
  if (!Array.isArray(input.events)) {
    throw new Error("events must be an array");
  }

  const minEvents =
    input.min_events_per_task === undefined ||
    input.min_events_per_task === null
      ? 3
      : input.min_events_per_task;
  if (
    typeof minEvents !== "number" ||
    !Number.isInteger(minEvents) ||
    minEvents < 1
  ) {
    throw new Error("min_events_per_task must be a positive integer");
  }

  const notes: string[] = [
    "backlog_mutated=false — rewrite proposals are advisory only",
    "store_mutated=false — Antiek-bench store not written",
    "usage events are caller-supplied only (no invent)",
  ];

  type Agg = {
    worked: number;
    failed: number;
    mixed: number;
    unknown: number;
    count: number;
  };
  const byTask = new Map<string, Agg>();
  const seen = new Set<string>();

  for (let i = 0; i < input.events.length; i++) {
    const e = input.events[i];
    if (!e || typeof e !== "object") {
      throw new Error(`events[${i}] must be an object`);
    }
    const eid = requireNonEmpty(e.event_id, `events[${i}].event_id`);
    if (seen.has(eid)) {
      throw new Error(`duplicate event_id: ${eid}`);
    }
    seen.add(eid);
    const task = requireNonEmpty(e.task, `events[${i}].task`);
    requireNonEmpty(e.model_id, `events[${i}].model_id`);
    if (!VALID_OUTCOME.has(e.outcome)) {
      throw new Error(
        `events[${i}].outcome must be worked|failed|mixed|unknown`,
      );
    }
    if (e.score !== undefined && e.score !== null) {
      if (
        typeof e.score !== "number" ||
        !Number.isFinite(e.score) ||
        e.score < 0 ||
        e.score > 1
      ) {
        throw new Error(
          `events[${i}].score must be finite in [0,1] when set`,
        );
      }
    }
    let agg = byTask.get(task);
    if (!agg) {
      agg = { worked: 0, failed: 0, mixed: 0, unknown: 0, count: 0 };
      byTask.set(task, agg);
    }
    agg.count += 1;
    if (e.outcome === "worked") agg.worked += 1;
    else if (e.outcome === "failed") agg.failed += 1;
    else if (e.outcome === "mixed") agg.mixed += 1;
    else agg.unknown += 1;
  }

  const event_count = input.events.length;
  const task_count = byTask.size;
  notes.push(`event_count=${event_count} · task_count=${task_count}`);

  const proposals: SubBenchmarkRewriteProposal[] = [];
  for (const [task, agg] of byTask) {
    if (agg.count < minEvents) {
      notes.push(
        `task=${task} skipped (events=${agg.count} < min=${minEvents})`,
      );
      continue;
    }
    let emphasis: SubBenchmarkRewriteProposal["emphasis"];
    let reason: string;
    if (agg.failed > agg.worked) {
      emphasis = "expand_failure_cases";
      reason = `failed=${agg.failed} > worked=${agg.worked} over ${agg.count} events`;
    } else if (agg.worked > agg.failed && agg.worked >= Math.ceil(agg.count / 2)) {
      emphasis = "hold_stable";
      reason = `worked=${agg.worked} dominates over ${agg.count} events`;
    } else if (agg.worked > 0 && agg.failed === 0) {
      emphasis = "expand_success_cases";
      reason = `all non-fail outcomes worked=${agg.worked} over ${agg.count} events`;
    } else {
      emphasis = "expand_failure_cases";
      reason = `mixed/unknown heavy over ${agg.count} events (failed=${agg.failed} worked=${agg.worked})`;
    }
    proposals.push({
      task,
      reason,
      emphasis,
      event_count: agg.count,
      failed_count: agg.failed,
      worked_count: agg.worked,
    });
  }

  // Stable order by task id
  proposals.sort((a, b) => a.task.localeCompare(b.task));
  const proposal_count = proposals.length;
  notes.push(`proposal_count=${proposal_count}`);

  const learn_ready = input.operator_ack && proposal_count >= 1;
  if (!input.operator_ack) {
    notes.push("learn_ready=false — operator_ack required");
  } else if (proposal_count === 0) {
    notes.push(
      "learn_ready=false — no tasks met min_events threshold (no invent proposals)",
    );
  } else {
    notes.push(
      "learn_ready=true — advisory rewrite proposals ready for operator review",
    );
  }

  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");

  return {
    week_id,
    event_count,
    task_count,
    proposals,
    proposal_count,
    learn_ready,
    backlog_mutated: false,
    store_mutated: false,
    notes,
    authority: "antiek_bench_weekly_usage_learn_compose_advisory",
  };
}

export function formatAntiekBenchWeeklyUsageLearnSummary(
  c: AntiekBenchWeeklyUsageLearnCompose,
): string {
  return (
    `learn_ready=${c.learn_ready} · proposals=${c.proposal_count} · ` +
    `events=${c.event_count} · backlog_mutated=false · store_mutated=false`
  );
}
