/**
 * Composer model projection client — per-prompt model choice + budget readout.
 *
 * Typed to the POST /settings/composer-projection/resolve route (PR 2058 Slice B),
 * which composes the advisory ranking + the authoritative CostProjection (PR 2057
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
  "call" | "input_token" | "output_token" | "http_request" | "local_operation";

export interface BoundedUsageInput {
  unit: UsageUnit;
  maximum: number;
}

export interface ComposerChoice {
  provider: string;
  model: string;
}

export interface ComposerProjectionRequest {
  task: ComposerDecisionTask;
  bounded_usage: BoundedUsageInput[];
  choice?: ComposerChoice | null;
  operation?: string;
  seam_id?: string;
}

export type QualityBasis = "measured" | "absent";
export type PricingStatus = "known" | "unknown";
export type ProjectionDisposition =
  "hold_eligible" | "zero_cost_receipt" | "ineligible";

export interface ComposerCandidateView {
  rank: number;
  tier: string;
  provider: string;
  model: string;
  quality_score: number | null;
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
  /** Exact server Decimal. Never coerce through an IEEE-754 number. */
  maximum_cost_usd: string;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const EXACT_NON_NEGATIVE_DECIMAL = /^(?:0|[1-9]\d*)(?:\.\d+)?(?:e[+-]?\d+)?$/i;
// Mirrors the backend's 1,000-place Decimal exponent bound with room for the
// coefficient, decimal point, exponent marker/sign, and exponent digits.
const MAX_EXACT_COST_LENGTH = 1_100;

async function readJson(res: Response): Promise<ComposerModelProjection> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(
      `composer projection API ${res.status}: ${text.slice(0, 200)}`,
    );
  }
  const body: unknown = await res.json();
  if (!isRecord(body)) {
    throw new Error("composer projection API returned an invalid response");
  }
  const chosen = body.chosen_projection;
  if (chosen !== null) {
    if (
      !isRecord(chosen) ||
      typeof chosen.maximum_cost_usd !== "string" ||
      chosen.maximum_cost_usd.length > MAX_EXACT_COST_LENGTH ||
      !EXACT_NON_NEGATIVE_DECIMAL.test(chosen.maximum_cost_usd) ||
      typeof chosen.reservation_cents !== "number" ||
      !Number.isSafeInteger(chosen.reservation_cents) ||
      chosen.reservation_cents < 0
    ) {
      throw new Error("composer projection API returned an invalid exact cost");
    }
  }
  return body as unknown as ComposerModelProjection;
}

export async function fetchComposerProjection(
  body: ComposerProjectionRequest,
): Promise<ComposerModelProjection> {
  const res = await apiFetch(
    `${API_BASE}/settings/composer-projection/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return readJson(res);
}
