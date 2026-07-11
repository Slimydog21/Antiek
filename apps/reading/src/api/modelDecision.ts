/**
 * Advisory model decision-tree client.
 *
 * Mirrors the PR #783 backend contract:
 *   POST /settings/model-decision/rank
 *
 * Authority is always "advisory" — never production dispatch. This client does
 * not call providers; it only ranks inventory the caller supplies.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type ModelTier = "reasoning" | "balanced" | "flash" | "unknown" | string;

export interface DecisionModelIn {
  model_id: string;
  provider?: string;
  tier?: ModelTier;
  usd_per_1k_tokens?: number | null;
  enabled?: boolean;
}

export interface RankedModelOut {
  model_id: string;
  provider: string;
  tier: string;
  score: number;
  rationale: string;
  projected_cost_usd_low: number | null;
  projected_cost_usd_high: number | null;
  would_exceed: boolean | null;
}

export interface DecisionTreeRankResponse {
  task: string;
  authority: string;
  recommended_model_id: string | null;
  remaining_usd: number | null;
  prompt_chars: number | null;
  notes: string[];
  ranked: RankedModelOut[];
}

export interface DecisionTreeRankRequest {
  task: string;
  models: DecisionModelIn[];
  remaining_usd?: number | null;
  prompt_chars?: number | null;
  bench_scores?: Record<string, Record<string, number>> | null;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`model-decision API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function rankModelsForTask(
  req: DecisionTreeRankRequest,
): Promise<DecisionTreeRankResponse> {
  const res = await apiFetch(`${API_BASE}/settings/model-decision/rank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task: req.task,
      models: req.models,
      remaining_usd: req.remaining_usd ?? null,
      prompt_chars: req.prompt_chars ?? null,
      bench_scores: req.bench_scores ?? null,
    }),
  });
  return readJson<DecisionTreeRankResponse>(res);
}

/** Pure display helpers — unit-tested without network. */

export function formatWouldExceed(value: boolean | null): string {
  if (value === null) return "unknown (remaining budget not provided)";
  if (value === true) return "would exceed remaining budget";
  return "within remaining budget";
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${value.toFixed(4)}`;
}

export function formatRemaining(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "unknown (not zero-faked)";
  }
  return `$${value.toFixed(4)}`;
}

export function authorityIsAdvisory(authority: string | null | undefined): boolean {
  return (authority ?? "").trim().toLowerCase() === "advisory";
}
