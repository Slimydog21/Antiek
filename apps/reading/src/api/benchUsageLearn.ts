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
  const weightsRaw = Array.isArray(o.task_weights) ? o.task_weights : [];
  const task_weights: TaskWeightProposal[] = weightsRaw.map((w) => {
    const row = (w && typeof w === "object" ? w : {}) as Record<string, unknown>;
    return {
      task: String(row.task ?? "general"),
      weight: Number(row.weight ?? 0),
      prior_weight:
        row.prior_weight === null || row.prior_weight === undefined
          ? null
          : Number(row.prior_weight),
      n_success: Number(row.n_success ?? 0),
      n_failure: Number(row.n_failure ?? 0),
      rationale: String(row.rationale ?? ""),
    };
  });
  return {
    week_id: String(o.week_id ?? ""),
    authority: "advisory",
    incomplete: Boolean(o.incomplete),
    notes: Array.isArray(o.notes) ? o.notes.map((n) => String(n)) : [],
    suggested_new_tasks: Array.isArray(o.suggested_new_tasks)
      ? o.suggested_new_tasks.map((t) => String(t))
      : [],
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
