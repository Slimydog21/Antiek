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

export interface NotDiamondPromotionGate {
  eligible: boolean;
  required_consecutive_weeks: number;
  evidence_week_ids: string[];
  reason: string;
}

export interface NotDiamondAdvisorRecommendation {
  advisor: "notdiamond";
  mode: "disabled" | "shadow" | "advisory";
  available: boolean;
  provider: string | null;
  model: string | null;
  tier: string | null;
  source:
    | "disabled"
    | "local_policy"
    | "notdiamond_candidate"
    | "advisor_unavailable"
    | "advisor_candidate_unavailable"
    | "advisor_cache_penalty";
  confidence: number | null;
  session_id: string | null;
  reason: string;
  cache_caveat: string | null;
  external_call_performed: boolean;
  notdiamond_would_call: boolean;
  promotion_gate: NotDiamondPromotionGate;
  notes: string[];
}

export interface NotDiamondAdvisorResponse {
  estimate: PromptCostEstimateResponse;
  recommendation: NotDiamondAdvisorRecommendation;
}

export interface AntiekBenchBestModelRow {
  task_class: string;
  provider: string;
  model: string;
  quality_score: number;
  estimated_cost_usd: number | null;
  actual_cost_usd: number | null;
  cost_per_acceptable_answer: number | null;
  latency_ms: number | null;
  route_receipt_ids: string[];
}

export interface AntiekBenchLatestResponse {
  available: boolean;
  scorecard_id: string | null;
  generated_at: string | null;
  week_id: string | null;
  mock_run: boolean | null;
  best_by_task_class: AntiekBenchBestModelRow[];
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

export async function fetchLatestAntiekBench(): Promise<AntiekBenchLatestResponse> {
  const res = await apiFetch(`${API_BASE}/settings/antiek-bench/latest`);
  return readJson<AntiekBenchLatestResponse>(res);
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

export async function estimateNotDiamondAdvisor(
  body: PromptCostEstimateRequest,
): Promise<NotDiamondAdvisorResponse> {
  const res = await apiFetch(`${API_BASE}/settings/router-advisor/notdiamond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<NotDiamondAdvisorResponse>(res);
}
