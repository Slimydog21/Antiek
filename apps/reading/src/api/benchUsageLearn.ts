/**
 * Antiek-bench usage-learn client (PR #804 contract).
 *
 * POST /settings/antiek-bench/usage-learn
 *
 * Proposes next-week sub-benchmark weights from injected usage outcomes.
 * Advisory only — never mutates antiek_bench authority.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface UsageEventInput {
  task?: string;
  success?: boolean | null;
  model_id?: string;
  notes?: string;
}

export interface TaskWeightProposal {
  task: string;
  weight: number;
  prior_weight: number | null;
  n_success: number;
  n_failure: number;
  rationale: string;
}

export interface UsageLearnProposal {
  week_id: string;
  authority: string;
  incomplete: boolean;
  notes: string[];
  suggested_new_tasks: string[];
  task_weights: TaskWeightProposal[];
}

export interface UsageLearnRequest {
  week_id?: string;
  usage_events?: UsageEventInput[];
  prior_weights?: Record<string, number> | null;
  min_weight?: number;
}

export class UsageLearnHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`usage-learn API ${status}: ${body.slice(0, 200)}`);
    this.name = "UsageLearnHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new UsageLearnHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

/**
 * Fail closed when authority is not advisory — usage-learn must never
 * present itself as production bench mutation authority.
 */
export function parseUsageLearnProposal(body: unknown): UsageLearnProposal {
  if (!body || typeof body !== "object") {
    throw new Error("usage-learn response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (o.authority !== "advisory") {
    throw new Error(
      "usage-learn response rejected: authority must be advisory",
    );
  }
  if (!Array.isArray(o.task_weights)) {
    throw new Error("usage-learn response rejected: task_weights must be an array");
  }
  if (typeof o.incomplete !== "boolean") {
    throw new Error("usage-learn response rejected: incomplete must be boolean");
  }
  if (typeof o.week_id !== "string") {
    throw new Error("usage-learn response rejected: week_id must be a string");
  }
  if (!Array.isArray(o.notes)) {
    throw new Error("usage-learn response rejected: notes must be an array");
  }
  if (!Array.isArray(o.suggested_new_tasks)) {
    throw new Error(
      "usage-learn response rejected: suggested_new_tasks must be an array",
    );
  }

  const task_weights: TaskWeightProposal[] = o.task_weights.map((w, idx) => {
    if (!w || typeof w !== "object") {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}] must be an object`,
      );
    }
    const row = w as Record<string, unknown>;
    if (typeof row.task !== "string" || !row.task.trim()) {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].task required`,
      );
    }
    if (typeof row.weight !== "number" || !Number.isFinite(row.weight)) {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].weight must be finite number`,
      );
    }
    if (row.weight < 0) {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].weight must be nonnegative`,
      );
    }
    let prior_weight: number | null;
    if (row.prior_weight === null || row.prior_weight === undefined) {
      prior_weight = null;
    } else if (
      typeof row.prior_weight === "number" &&
      Number.isFinite(row.prior_weight)
    ) {
      prior_weight = row.prior_weight;
    } else {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].prior_weight invalid`,
      );
    }
    if (typeof row.n_success !== "number" || !Number.isFinite(row.n_success)) {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].n_success must be finite number`,
      );
    }
    if (typeof row.n_failure !== "number" || !Number.isFinite(row.n_failure)) {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].n_failure must be finite number`,
      );
    }
    if (typeof row.rationale !== "string") {
      throw new Error(
        `usage-learn response rejected: task_weights[${idx}].rationale must be string`,
      );
    }
    return {
      task: row.task,
      weight: row.weight,
      prior_weight,
      n_success: row.n_success,
      n_failure: row.n_failure,
      rationale: row.rationale,
    };
  });
  return {
    week_id: o.week_id,
    authority: "advisory",
    incomplete: o.incomplete,
    notes: o.notes.map((n) => String(n)),
    suggested_new_tasks: o.suggested_new_tasks.map((t) => String(t)),
    task_weights,
  };
}

export async function postUsageLearn(
  req: UsageLearnRequest,
): Promise<UsageLearnProposal> {
  const res = await apiFetch(`${API_BASE}/settings/antiek-bench/usage-learn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      week_id: req.week_id ?? "",
      usage_events: (req.usage_events ?? []).map((e) => ({
        task: e.task ?? "general",
        success: e.success ?? null,
        model_id: e.model_id ?? "",
        notes: e.notes ?? "",
      })),
      prior_weights: req.prior_weights ?? null,
      min_weight: req.min_weight ?? 0.05,
    }),
  });
  const raw = await readOkBody(res);
  return parseUsageLearnProposal(raw);
}

export function formatAuthority(value: string | null | undefined): string {
  if (value === "advisory") return "advisory (proposal only)";
  if (!value) return "unknown authority";
  return `unexpected authority: ${value}`;
}

export function formatWeight(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "unknown";
  }
  return value.toFixed(4);
}
