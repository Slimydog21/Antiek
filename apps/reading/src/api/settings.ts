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
  task_kind?:
    | "research_question"
    | "reading_highlight"
    | "midnight_oil"
    | "synthesis"
    | "verification"
    | null;
  role?: string | null;
  route_mode?:
    | "manual"
    | "auto_quality"
    | "auto_balanced"
    | "auto_cost"
    | "auto_latency";
  manual_provider?: string | null;
  manual_model?: string | null;
  session_cache_key?: string | null;
  provider?: string | null;
  model?: string | null;
  tier?: string | null;
  prompt_chars?: number | null;
  input_chars: number;
  expected_output_tokens: number;
}

export interface PromptCostCandidate {
  provider: string;
  model: string;
  tier: string;
  fallback_chain_index: number;
  estimated_usd_low: number | null;
  estimated_usd_high: number | null;
  pricing_known: boolean;
  cache_status: "warm" | "cold" | "unknown";
  selection_reason: string;
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
  task_kind: string | null;
  role: string | null;
  route_mode:
    | "manual"
    | "auto_quality"
    | "auto_balanced"
    | "auto_cost"
    | "auto_latency"
    | null;
  selected_candidate: PromptCostCandidate | null;
  candidates: PromptCostCandidate[];
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
