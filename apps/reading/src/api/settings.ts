import { API_BASE, apiFetch } from "../lib/api";

export interface ModelRow {
  provider_id: string;
  registered: boolean;
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
  eligible: boolean;
  quality_score: number;
  quality_basis: "measured" | "static_prior";
  benchmark_samples: number | null;
  estimated_usd_low: number | null;
  estimated_usd_high: number | null;
  would_exceed_budget: boolean | null;
}

export interface ModelDecisionResponse {
  authority: "advisory";
  task: ModelDecisionTask;
  recommended_tier: string | null;
  benchmark_status: "measured" | "unavailable";
  benchmark_generated_at: string | null;
  candidates: ModelDecisionCandidate[];
  notes: string[];
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
  return readJson<ModelDecisionResponse>(res);
}
