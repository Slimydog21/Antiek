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

/** Process-local decision-tree driver selection (install / read / clear). */
export interface DecisionTreeSelectionResponse {
  model_id: string | null;
  provider_id: string | null;
  installed: boolean;
  notes: string[];
  source: string;
}

export async function fetchDecisionTreeSelection(): Promise<DecisionTreeSelectionResponse> {
  const res = await apiFetch(`${API_BASE}/settings/decision-tree`);
  return readJson<DecisionTreeSelectionResponse>(res);
}

export async function installDecisionTreeSelection(body: {
  model_id: string;
  provider_id?: string | null;
}): Promise<DecisionTreeSelectionResponse> {
  const res = await apiFetch(`${API_BASE}/settings/decision-tree`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<DecisionTreeSelectionResponse>(res);
}

export async function clearDecisionTreeSelection(): Promise<DecisionTreeSelectionResponse> {
  const res = await apiFetch(`${API_BASE}/settings/decision-tree`, {
    method: "DELETE",
  });
  return readJson<DecisionTreeSelectionResponse>(res);
}

/** Weekly Antiek-bench usage summary (recorded engagement outcomes). */
export type UsageTaskClassBucket = {
  worked?: number;
  failed?: number;
  total?: number;
};

export type AntiekBenchUsageSummaryResponse = {
  event_count: number;
  by_task_class: Record<string, UsageTaskClassBucket>;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchAntiekBenchUsageSummary(opts?: {
  includeHtml?: boolean;
}): Promise<AntiekBenchUsageSummaryResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(`${API_BASE}/settings/antiek-bench/usage-summary${q}`);
  return readJson<AntiekBenchUsageSummaryResponse>(res);
}

/** Suite rewrite proposal from recorded usage — never auto-promoted. */
export type AntiekBenchSuiteProposalResponse = {
  has_proposal: boolean;
  proposal_id: string | null;
  status: string | null;
  base_suite_version: string | null;
  proposed_suite_version: string | null;
  active_suite_version: string | null;
  active_suite_unchanged: boolean;
  auto_promoted: boolean;
  rationale: string | null;
  added_item_ids: string[];
  event_count: number;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchAntiekBenchSuiteProposal(opts?: {
  includeHtml?: boolean;
}): Promise<AntiekBenchSuiteProposalResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(
    `${API_BASE}/settings/antiek-bench/suite-proposal${q}`,
  );
  return readJson<AntiekBenchSuiteProposalResponse>(res);
}

/** NotDiamond advisory posture — never authority over dispatch. */
export type NotDiamondAdvisoryResponse = {
  advisory_allowed: boolean;
  advisory_verdict: string;
  authority_allowed: boolean;
  authority_rejected: boolean;
  authority_verdict: string;
  dispatch_owner: string;
  notdiamond_is_dispatch_authority: boolean;
  kill_switch_env: string;
  kill_switch_enabled: boolean;
  default_off: boolean;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  verdict_date: string;
  notes: string[];
  html?: string | null;
};

export async function fetchNotDiamondAdvisory(opts?: {
  includeHtml?: boolean;
}): Promise<NotDiamondAdvisoryResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(`${API_BASE}/settings/notdiamond/advisory${q}`);
  return readJson<NotDiamondAdvisoryResponse>(res);
}
