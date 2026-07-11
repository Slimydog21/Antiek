/**
 * Usage bar + prompt projection client (PR #795 contract).
 *
 * POST /settings/usage-bar/project
 *
 * Honesty: remaining_usd / would_exceed / fraction_used are null when unknown
 * — never invent $0 remaining.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface UsageBarSnapshot {
  daily_cap_usd: number | null;
  spent_usd: number | null;
  remaining_usd: number | null;
  over_budget: boolean | null;
  fraction_used: number | null;
  spend_basis: string;
  notes: string[];
}

export interface PromptProjectionSnapshot {
  projected_cost_usd_low: number | null;
  projected_cost_usd_high: number | null;
  remaining_before_usd: number | null;
  remaining_after_high_usd: number | null;
  would_exceed: boolean | null;
  notes: string[];
}

export interface UsageBarProjectResponse {
  usage_bar: UsageBarSnapshot;
  prompt_projection?: PromptProjectionSnapshot;
}

export interface UsageBarProjectRequest {
  daily_cap_usd?: number | null;
  spent_usd?: number | null;
  spend_basis?: string;
  projected_cost_usd_low?: number | null;
  projected_cost_usd_high?: number | null;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`usage-bar API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function projectUsageBar(
  req: UsageBarProjectRequest,
): Promise<UsageBarProjectResponse> {
  const res = await apiFetch(`${API_BASE}/settings/usage-bar/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      daily_cap_usd: req.daily_cap_usd ?? null,
      spent_usd: req.spent_usd ?? null,
      spend_basis: req.spend_basis ?? "reserved_estimate",
      projected_cost_usd_low: req.projected_cost_usd_low ?? null,
      projected_cost_usd_high: req.projected_cost_usd_high ?? null,
    }),
  });
  return readJson<UsageBarProjectResponse>(res);
}

/** Pure display helpers — unit-tested without network. */

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unknown (not zero-faked)";
  return `$${value.toFixed(4)}`;
}

export function formatFractionUsed(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unknown";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatWouldExceed(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "unknown (remaining or projection incomplete)";
  }
  if (value === true) return "would exceed remaining budget";
  return "within remaining budget";
}

export function formatOverBudget(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return "unknown";
  return value ? "over budget" : "within budget";
}
