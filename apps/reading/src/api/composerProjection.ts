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

export type QualityBasis = "measured" | "static_prior";
export type PricingStatus = "known" | "unknown";
export type ProjectionDisposition =
  "hold_eligible" | "zero_cost_receipt" | "ineligible";

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
  /** Exact server Decimal. Never coerce through an IEEE-754 number. */
  maximum_cost_usd: string;
  reservation_cents: number;
  disposition: ProjectionDisposition;
  ineligibility: string | null;
}

export interface ComposerFallbackRouteProjection {
  maximum_cost_usd: string;
  reservation_cents: number;
  disposition: ProjectionDisposition;
  ineligibility: string | null;
  rate_snapshot: string;
}

export interface ComposerFallbackRoute {
  fallback_index: number;
  provider: string;
  model: string;
  registered: boolean;
  projection: ComposerFallbackRouteProjection;
  hard_ceiling_eligible: boolean;
  execution_status: string;
}

export interface ComposerFallbackPlan {
  authority: "advisory_fallback_plan";
  tier: string;
  status: "executable" | "blocked";
  maximum_chain_exposure_cents: number | null;
  would_exceed_budget: boolean | null;
  routes: ComposerFallbackRoute[];
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
  fallback_plan: ComposerFallbackPlan | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const EXACT_NON_NEGATIVE_DECIMAL = /^(?:0|[1-9]\d*)(?:\.\d+)?(?:e[+-]?\d+)?$/i;
// Mirrors the backend's 1,000-place Decimal exponent bound with room for the
// coefficient, decimal point, exponent marker/sign, and exponent digits.
const MAX_EXACT_COST_LENGTH = 1_100;
const EXECUTION_STATUSES = new Set([
  "executable",
  "blocked_unknown_pricing",
  "blocked_idempotency_unproven",
  "blocked_reconciliation_unproven",
  "blocked_hidden_retries",
  "blocked_provider_qualification",
  "blocked_selection_authority",
  "blocked_no_hard_ceiling_adapter",
  "blocked_hard_ceiling_adapter_mismatch",
]);

function validExactCost(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length <= MAX_EXACT_COST_LENGTH &&
    EXACT_NON_NEGATIVE_DECIMAL.test(value)
  );
}

function validCents(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function validIdentity(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 256 &&
    value.trim() === value
  );
}

function validateFallbackPlan(
  value: unknown,
): asserts value is ComposerFallbackPlan | null {
  if (value === null) return;
  if (
    !isRecord(value) ||
    value.authority !== "advisory_fallback_plan" ||
    !validIdentity(value.tier) ||
    (value.status !== "executable" && value.status !== "blocked") ||
    !Array.isArray(value.routes) ||
    value.routes.length < 1 ||
    value.routes.length > 16
  ) {
    throw new Error(
      "composer projection API returned an invalid fallback plan",
    );
  }
  const identities = new Set<string>();
  const reservations: number[] = [];
  let executable = true;
  value.routes.forEach((raw, index) => {
    if (
      !isRecord(raw) ||
      raw.fallback_index !== index ||
      !validIdentity(raw.provider) ||
      !validIdentity(raw.model) ||
      typeof raw.registered !== "boolean" ||
      typeof raw.hard_ceiling_eligible !== "boolean" ||
      typeof raw.execution_status !== "string" ||
      !EXECUTION_STATUSES.has(raw.execution_status) ||
      raw.hard_ceiling_eligible !== (raw.execution_status === "executable") ||
      !isRecord(raw.projection)
    ) {
      throw new Error(
        "composer projection API returned an invalid fallback route",
      );
    }
    const routeKey = JSON.stringify([raw.provider, raw.model]);
    if (identities.has(routeKey)) {
      throw new Error(
        "composer projection API returned duplicate fallback routes",
      );
    }
    identities.add(routeKey);
    const projected = raw.projection;
    if (
      !validExactCost(projected.maximum_cost_usd) ||
      !validCents(projected.reservation_cents) ||
      !["hold_eligible", "zero_cost_receipt", "ineligible"].includes(
        String(projected.disposition),
      ) ||
      (projected.ineligibility !== null &&
        !validIdentity(projected.ineligibility)) ||
      !validIdentity(projected.rate_snapshot)
    ) {
      throw new Error(
        "composer projection API returned an invalid fallback cost",
      );
    }
    reservations.push(projected.reservation_cents);
    executable &&=
      raw.registered &&
      raw.hard_ceiling_eligible &&
      projected.disposition === "hold_eligible";
  });
  const exposure = value.maximum_chain_exposure_cents;
  if (
    (exposure !== null && !validCents(exposure)) ||
    (value.would_exceed_budget !== null &&
      typeof value.would_exceed_budget !== "boolean") ||
    value.status !== (executable ? "executable" : "blocked") ||
    (executable && exposure !== Math.max(...reservations)) ||
    (!executable && (exposure !== null || value.would_exceed_budget !== null))
  ) {
    throw new Error(
      "composer projection API returned contradictory fallback authority",
    );
  }
}

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
      !validExactCost(chosen.maximum_cost_usd) ||
      !validCents(chosen.reservation_cents)
    ) {
      throw new Error("composer projection API returned an invalid exact cost");
    }
  }
  validateFallbackPlan(body.fallback_plan);
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
