/**
 * Antiek-bench recursive rewrite proposal (pure client).
 *
 * Operator vision: weekly bench learns from usage patterns (what worked /
 * didn't) and proposes sub-benchmark rewrites as the platform expands.
 *
 * This pure layer never applies production bench changes (applied=false).
 */

export type UsageOutcome = "worked" | "failed" | "mixed" | "unknown";

export interface UsagePattern {
  task_family: string;
  model_id: string;
  outcome: UsageOutcome;
  /** Optional sample size for weighting. */
  n?: number;
}

export interface SubBenchmarkProposal {
  sub_benchmark_id: string;
  task_family: string;
  rationale: string;
  /** Models that underperformed or need differentiation. */
  focus_models: string[];
  /** Priority weight derived from failure/mixed volume. */
  priority: number;
}

export interface BenchRewriteProposal {
  week_label: string;
  proposals: SubBenchmarkProposal[];
  /** Always false — advisory proposal only. */
  applied: false;
  notes: string[];
  authority: "antiek_bench_rewrite_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Propose recursive Antiek-bench sub-benchmark rewrites from usage patterns.
 * Never invents outcomes; never applies production changes.
 */
export function proposeAntiekBenchRecursiveRewrite(input: {
  week_label: string;
  patterns: UsagePattern[];
}): BenchRewriteProposal {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const week = requireNonEmpty(input.week_label, "week_label");
  if (!Array.isArray(input.patterns)) {
    throw new Error("patterns must be an array");
  }

  const notes: string[] = [
    "applied=false — proposal only, production bench not mutated",
  ];

  if (input.patterns.length === 0) {
    notes.push("no usage patterns — empty proposals (no invent)");
    return {
      week_label: week,
      proposals: [],
      applied: false,
      notes,
      authority: "antiek_bench_rewrite_advisory",
    };
  }

  // Aggregate failure/mixed weight per task_family + track models.
  type Agg = {
    failWeight: number;
    workWeight: number;
    models: Map<string, number>;
  };
  const byFamily = new Map<string, Agg>();

  for (let i = 0; i < input.patterns.length; i++) {
    const p = input.patterns[i];
    if (!p || typeof p !== "object") {
      throw new Error(`patterns[${i}] must be an object`);
    }
    const task = requireNonEmpty(p.task_family, `patterns[${i}].task_family`);
    const model = requireNonEmpty(p.model_id, `patterns[${i}].model_id`);
    const outcome = p.outcome;
    if (
      outcome !== "worked" &&
      outcome !== "failed" &&
      outcome !== "mixed" &&
      outcome !== "unknown"
    ) {
      throw new Error(
        `patterns[${i}].outcome must be worked|failed|mixed|unknown`,
      );
    }
    let n = 1;
    if (p.n !== undefined && p.n !== null) {
      if (typeof p.n !== "number" || !Number.isFinite(p.n) || p.n <= 0) {
        throw new Error(`patterns[${i}].n must be positive finite when set`);
      }
      n = p.n;
    }
    let agg = byFamily.get(task);
    if (!agg) {
      agg = { failWeight: 0, workWeight: 0, models: new Map() };
      byFamily.set(task, agg);
    }
    if (outcome === "failed") {
      agg.failWeight += n;
      agg.models.set(model, (agg.models.get(model) ?? 0) + n);
    } else if (outcome === "mixed") {
      agg.failWeight += n * 0.5;
      agg.models.set(model, (agg.models.get(model) ?? 0) + n * 0.5);
    } else if (outcome === "worked") {
      agg.workWeight += n;
    } else {
      // unknown — do not invent failure signal
      notes.push(
        `patterns[${i}] outcome=unknown ignored for rewrite weight (no invent failure)`,
      );
    }
  }

  const proposals: SubBenchmarkProposal[] = [];
  for (const [task_family, agg] of byFamily) {
    if (agg.failWeight <= 0) {
      continue;
    }
    const focus_models = [...agg.models.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([m]) => m);
    const priority = agg.failWeight;
    if (!Number.isFinite(priority)) {
      throw new Error("priority overflowed to non-finite");
    }
    proposals.push({
      sub_benchmark_id: `sb_${task_family.replace(/[^a-zA-Z0-9_-]+/g, "_")}`,
      task_family,
      rationale: `Usage showed fail/mixed weight=${priority} vs worked=${agg.workWeight}; differentiate models on this family.`,
      focus_models,
      priority,
    });
  }

  proposals.sort((a, b) => b.priority - a.priority);
  notes.push(`proposals=${proposals.length} from ${byFamily.size} task families`);
  notes.push("applied=false");

  return {
    week_label: week,
    proposals,
    applied: false,
    notes,
    authority: "antiek_bench_rewrite_advisory",
  };
}

export function formatBenchRewriteSummary(p: BenchRewriteProposal): string {
  return (
    `week=${p.week_label} · proposals=${p.proposals.length} · applied=false`
  );
}
