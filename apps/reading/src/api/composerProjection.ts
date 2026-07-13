/**
 * Composer model projection client — per-prompt model choice + budget readout.
 *
 * Typed to the POST /settings/composer-projection/resolve route (#2058 Slice B),
 * which composes the advisory ranking + the authoritative CostProjection (#2057
 * Slice A) into one ComposerModelProjection. This client never re-derives; it is
 * the typed transport the `<ModelDecisionBar>` component renders.
 *
 * Honesty rules (load-bearing, mirror the route/substrate):
 *   * Unknown pricing (`estimated_usd_low/high == null`) is "unknown", never $0.00.
 *   * `would_exceed_budget` is server-derived; null when unmeasurable (never false).
 *   * `quality_basis` is carried so the UI never mistakes a prior for a measurement.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type ComposerDecisionTask =
  | "deep_research"
  | "research_synthesis"
  | "reading"
  | "twin_note"
  | "writing"
  | "multimedia"
  | "general";

export type UsageUnit =
  | "call"
  | "input_token"
  | "output_token"
  | "http_request"
  | "local_operation";

export interface BoundedUsageInput {
  unit: UsageUnit;
  maximum: number;
}

export interface ComposerCandidateInput {
  tier: string;
  provider: string;
  model: string;
  ready: boolean;
  estimated_usd_low?: number | null;
  estimated_usd_high?: number | null;
  would_exceed_budget?: boolean | null;
  benchmark_score?: number | null;
  benchmark_samples?: number | null;
}

export interface ComposerChoice {
  provider: string;
  model: string;
}

export interface ComposerProjectionRequest {
  task: ComposerDecisionTask;
  candidates: ComposerCandidateInput[];
  bounded_usage: BoundedUsageInput[];
  choice?: ComposerChoice | null;
  operation?: string;
  seam_id?: string;
}

export type QualityBasis = "measured" | "static_prior";
export type PricingStatus = "known" | "unknown";
export type ProjectionDisposition =
  | "hold_eligible"
  | "zero_cost_receipt"
  | "ineligible";

export interface ComposerCandidateView {
  rank: number;
  tier: string;
  provider: string;
  model: string;
  quality_score: number;
  quality_basis: QualityBasis;
  eligible: boolean;
  pricing_status: PricingStatus;
  estimated_usd_low: number | null;
  estimated_usd_high: number | null;
}

export interface ComposerChosenProjection {
  seam_id: string;
  provider: string;
  model: string;
  operation: string;
  maximum_cost_usd: number;
  reservation_cents: number;
  disposition: ProjectionDisposition;
  ineligibility: string | null;
}

export interface ComposerModelProjection {
  task: ComposerDecisionTask;
  recommended_tier: string | null;
  ranked_candidates: ComposerCandidateView[];
  budget: {
    daily_cap_usd: number | null;
    spent_usd: number | null;
  };
  remaining_usd: number | null;
  chosen_provider: string | null;
  chosen_model: string | null;
  chosen_projection: ComposerChosenProjection | null;
  would_exceed_budget: boolean | null;
  pricing_status: PricingStatus;
  authority: string;
  notes: string[];
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(
      `composer projection API ${res.status}: ${text.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchComposerProjection(
  body: ComposerProjectionRequest,
): Promise<ComposerModelProjection> {
  const res = await apiFetch(`${API_BASE}/settings/composer-projection/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<ComposerModelProjection>(res);
}
