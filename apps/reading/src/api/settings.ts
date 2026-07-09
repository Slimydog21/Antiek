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

/** Depth-tier presets: flash | pro | wrestle (process-local). */
export type DepthTierPreset = {
  depth_tier: string;
  label: string;
  description: string;
  dispatch_tier: string;
  task_class: string;
  default_input_chars: number;
  default_expected_output_tokens: number;
  competitor_posture: string;
};

export type DepthTierResponse = {
  active_depth_tier: string | null;
  active_preset: DepthTierPreset | null;
  presets: DepthTierPreset[];
  projection_hints: {
    tier?: string;
    input_chars?: number;
    expected_output_tokens?: number;
    task_class?: string;
  } | null;
  decision_tree_install?: Record<string, unknown> | null;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchDepthTiers(opts?: {
  includeHtml?: boolean;
}): Promise<DepthTierResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(`${API_BASE}/settings/depth-tier${q}`);
  return readJson<DepthTierResponse>(res);
}

export async function applyDepthTier(opts: {
  depth_tier: string;
  model_id?: string | null;
  provider_id?: string | null;
  install_driver?: boolean;
  includeHtml?: boolean;
}): Promise<DepthTierResponse> {
  const res = await apiFetch(`${API_BASE}/settings/depth-tier`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      depth_tier: opts.depth_tier,
      model_id: opts.model_id ?? null,
      provider_id: opts.provider_id ?? null,
      install_driver: Boolean(opts.install_driver),
      include_html: Boolean(opts.includeHtml),
    }),
  });
  return readJson<DepthTierResponse>(res);
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

/** Weekly Antiek-bench leaderboard (offline runs only; advisory model ranking). */
export type AntiekBenchLeaderboardModelRow = {
  model_id: string;
  mean_score?: number;
  by_task_class?: Record<string, number>;
  run_count?: number;
};

export type AntiekBenchLeaderboardResponse = {
  week_id: string;
  models: AntiekBenchLeaderboardModelRow[];
  task_classes: string[];
  run_count: number;
  suite_versions: string[];
  recommended_model_id: string | null;
  recommended_mean_score: number | null;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchAntiekBenchLeaderboard(opts: {
  weekId: string;
  includeHtml?: boolean;
}): Promise<AntiekBenchLeaderboardResponse> {
  const params = new URLSearchParams({ week_id: opts.weekId });
  if (opts.includeHtml) params.set("include_html", "true");
  const res = await apiFetch(
    `${API_BASE}/settings/antiek-bench/leaderboard?${params.toString()}`,
  );
  return readJson<AntiekBenchLeaderboardResponse>(res);
}

/** Competitive dogfood fixtures listing (offline; never auto-promoted). */
export type AntiekBenchDogfoodFixturesResponse = {
  suite_version: string;
  label: string;
  item_count: number;
  by_task_class: Record<string, number>;
  items: Array<{
    item_id: string;
    task_class: string;
    prompt: string;
  }>;
  auto_promoted: boolean;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function fetchAntiekBenchDogfoodFixtures(opts?: {
  includeHtml?: boolean;
}): Promise<AntiekBenchDogfoodFixturesResponse> {
  const q = opts?.includeHtml ? "?include_html=true" : "";
  const res = await apiFetch(
    `${API_BASE}/settings/antiek-bench/dogfood-fixtures${q}`,
  );
  return readJson<AntiekBenchDogfoodFixturesResponse>(res);
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

/** Explicit operator approve/reject for a suite proposal (never implicit). */
export type AntiekBenchSuiteApproveResponse = {
  ok: boolean;
  proposal_id: string | null;
  status: string | null;
  approved: boolean;
  promoted: boolean;
  active_suite_version: string | null;
  active_suite_before: string | null;
  proposed_suite_version: string | null;
  view_format: "html" | string;
  settings_panel: string;
  source: string;
  notes: string[];
  html?: string | null;
};

export async function approveAntiekBenchSuiteProposal(opts: {
  proposal_id: string;
  approve: boolean;
  includeHtml?: boolean;
}): Promise<AntiekBenchSuiteApproveResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/antiek-bench/suite-proposal/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        proposal_id: opts.proposal_id,
        approve: opts.approve,
        include_html: Boolean(opts.includeHtml),
      }),
    },
  );
  return readJson<AntiekBenchSuiteApproveResponse>(res);
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
