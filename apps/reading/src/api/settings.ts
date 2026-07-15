import { API_BASE, apiFetch } from "../lib/api";

export interface ModelRow {
  provider_id: string;
  ready: boolean;
  tier_bindings: string[];
  primary_model: string | null;
  notes: string | null;
}

export interface ModelsResponse {
  models: ModelRow[];
  count: number;
  providers_ready: boolean;
  source: string;
}

export interface BudgetResponse {
  daily_cap_usd: number | null;
  spent_usd: number | null;
  remaining_usd: number | null;
  spent_status: "known" | "unknown" | "no_cap";
  cap_env: string | null;
  notes: string[];
}

export interface PromptCostEstimateRequest {
  provider?: string | null;
  model?: string | null;
  tier?: string | null;
  input_chars: number;
  expected_output_tokens: number;
}

export interface PromptCostEstimateResponse {
  estimated_usd_low: number | null;
  estimated_usd_high: number | null;
  would_exceed_budget: boolean | null;
  pricing_known: boolean;
  notes: string[];
  assumed_input_tokens: number;
  assumed_output_tokens: number;
  tier: string | null;
  provider: string | null;
  model: string | null;
}

export type ModelDecisionTask =
  | "deep_research"
  | "research_synthesis"
  | "reading"
  | "twin_note"
  | "writing"
  | "multimedia"
  | "general";

export interface ModelDecisionCandidate {
  rank: number;
  tier: string;
  provider: string;
  model: string;
  ready: boolean;
  operationally_eligible: boolean;
  quality_score: number | null;
  quality_basis: "measured" | "absent";
  benchmark_samples: number | null;
  estimated_usd_low: number | null;
  estimated_usd_high: number | null;
  would_exceed_budget: boolean | null;
}

export interface ModelDecisionResponse {
  authority: "advisory";
  task: ModelDecisionTask;
  recommended_tier: string | null;
  recommendation_status?:
    | "measured"
    | "insufficient_measured_evidence"
    | "no_operationally_eligible_candidate";
  benchmark_status: "measured" | "unavailable";
  benchmark_generated_at: string | null;
  benchmark_measured_candidates?: number;
  benchmark_operational_candidates?: number;
  candidates: ModelDecisionCandidate[];
  notes: string[];
}

const MODEL_DECISION_TASKS: ReadonlySet<string> = new Set([
  "deep_research",
  "research_synthesis",
  "reading",
  "twin_note",
  "writing",
  "multimedia",
  "general",
]);

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isModelDecisionCandidate(value: unknown): value is ModelDecisionCandidate {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.rank === "number" &&
    Number.isFinite(candidate.rank) &&
    typeof candidate.tier === "string" &&
    typeof candidate.provider === "string" &&
    typeof candidate.model === "string" &&
    typeof candidate.ready === "boolean" &&
    typeof candidate.operationally_eligible === "boolean" &&
    isNullableFiniteNumber(candidate.quality_score) &&
    (candidate.quality_basis === "measured" || candidate.quality_basis === "absent") &&
    isNullableFiniteNumber(candidate.benchmark_samples) &&
    isNullableFiniteNumber(candidate.estimated_usd_low) &&
    isNullableFiniteNumber(candidate.estimated_usd_high) &&
    (candidate.would_exceed_budget === null ||
      typeof candidate.would_exceed_budget === "boolean")
  );
}

export function isModelDecisionResponse(value: unknown): value is ModelDecisionResponse {
  if (typeof value !== "object" || value === null) return false;
  const response = value as Record<string, unknown>;
  const recommendationStatus = response.recommendation_status;
  return (
    response.authority === "advisory" &&
    typeof response.task === "string" &&
    MODEL_DECISION_TASKS.has(response.task) &&
    (response.recommended_tier === null ||
      typeof response.recommended_tier === "string") &&
    (recommendationStatus === undefined ||
      recommendationStatus === "measured" ||
      recommendationStatus === "insufficient_measured_evidence" ||
      recommendationStatus === "no_operationally_eligible_candidate") &&
    (response.benchmark_status === "measured" ||
      response.benchmark_status === "unavailable") &&
    (response.benchmark_generated_at === null ||
      typeof response.benchmark_generated_at === "string") &&
    (response.benchmark_measured_candidates === undefined ||
      (typeof response.benchmark_measured_candidates === "number" &&
        Number.isFinite(response.benchmark_measured_candidates))) &&
    (response.benchmark_operational_candidates === undefined ||
      (typeof response.benchmark_operational_candidates === "number" &&
        Number.isFinite(response.benchmark_operational_candidates))) &&
    Array.isArray(response.candidates) &&
    response.candidates.every(isModelDecisionCandidate) &&
    Array.isArray(response.notes) &&
    response.notes.every((note) => typeof note === "string")
  );
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`settings API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function fetchSettingsModels(): Promise<ModelsResponse> {
  const res = await apiFetch(`${API_BASE}/settings/models`);
  return readJson<ModelsResponse>(res);
}

export async function fetchSettingsBudget(): Promise<BudgetResponse> {
  const res = await apiFetch(`${API_BASE}/settings/budget`);
  return readJson<BudgetResponse>(res);
}

export async function estimatePromptCost(
  body: PromptCostEstimateRequest,
): Promise<PromptCostEstimateResponse> {
  const res = await apiFetch(`${API_BASE}/settings/prompt-cost-estimate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<PromptCostEstimateResponse>(res);
}

export async function fetchModelDecision(body: {
  task: ModelDecisionTask;
  input_chars: number;
  expected_output_tokens: number;
}): Promise<ModelDecisionResponse> {
  const res = await apiFetch(`${API_BASE}/settings/model-decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload: unknown = await readJson<unknown>(res);
  if (!isModelDecisionResponse(payload)) {
    throw new Error("settings API returned an invalid model-decision response");
  }
  return payload;
}
