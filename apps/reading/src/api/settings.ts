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
  reserved_estimated_usd: number | null;
  spend_basis: "unknown" | "reserved_estimate";
  enforcement_cap_usd: number | null;
  enforcement_cap_env: string | null;
  caps_aligned: boolean | null;
  over_budget: boolean | null;
  over_budget_usd: number | null;
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

export type FallbackReceiptRouteState =
  | "unattempted"
  | "reserved_not_sent"
  | "dispatch_possible"
  | "unknown"
  | "released"
  | "settled";

export interface FallbackReceiptRoute {
  fallback_index: number;
  provider: string;
  model: string;
  seam_id: string;
  operation: string;
  projected_max_cents: number;
  state: FallbackReceiptRouteState;
  actual_cents: number | null;
  resolved_at: string | null;
  settlement_evidence_sha256: string | null;
  settlement_intent_sha256: string | null;
}

export interface FallbackReceiptChain {
  chain_id: string;
  manifest_sha256: string;
  outcome:
    "unattempted" | "in_progress" | "ambiguous" | "settled" | "exhausted";
  routes: FallbackReceiptRoute[];
  created_at: string;
}

export interface FallbackReceiptHistoryResponse {
  authority: "read_only_fallback_receipt_history";
  items: FallbackReceiptChain[];
  next_cursor: string | null;
}

const SHA256 = /^[0-9a-f]{64}$/;
const ROUTE_STATES = new Set<FallbackReceiptRouteState>([
  "unattempted",
  "reserved_not_sent",
  "dispatch_possible",
  "unknown",
  "released",
  "settled",
]);
const CHAIN_OUTCOMES = new Set([
  "unattempted",
  "in_progress",
  "ambiguous",
  "settled",
  "exhausted",
]);

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("fallback receipt history has an invalid shape");
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, expected: string[]): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (
    actual.length !== wanted.length ||
    actual.some((key, index) => key !== wanted[index])
  ) {
    throw new Error("fallback receipt history has unexpected fields");
  }
}

function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function nullableString(value: unknown): value is string | null {
  return value === null || nonEmpty(value);
}

function validateFallbackReceiptRoute(
  value: unknown,
  index: number,
): FallbackReceiptRoute {
  const route = record(value);
  exactKeys(route, [
    "fallback_index",
    "provider",
    "model",
    "seam_id",
    "operation",
    "projected_max_cents",
    "state",
    "actual_cents",
    "resolved_at",
    "settlement_evidence_sha256",
    "settlement_intent_sha256",
  ]);
  if (
    route.fallback_index !== index ||
    !nonEmpty(route.provider) ||
    !nonEmpty(route.model) ||
    !nonEmpty(route.seam_id) ||
    !nonEmpty(route.operation) ||
    !Number.isSafeInteger(route.projected_max_cents) ||
    (route.projected_max_cents as number) < 1 ||
    !ROUTE_STATES.has(route.state as FallbackReceiptRouteState) ||
    !(
      route.actual_cents === null ||
      (Number.isSafeInteger(route.actual_cents) &&
        (route.actual_cents as number) >= 0)
    ) ||
    !nullableString(route.resolved_at)
  ) {
    throw new Error("fallback receipt route is invalid");
  }
  const settled = route.state === "settled";
  const released = route.state === "released";
  if (
    settled !== (route.actual_cents !== null) ||
    (settled || released) !== (route.resolved_at !== null) ||
    settled !==
      (typeof route.settlement_evidence_sha256 === "string" &&
        SHA256.test(route.settlement_evidence_sha256)) ||
    settled !==
      (typeof route.settlement_intent_sha256 === "string" &&
        SHA256.test(route.settlement_intent_sha256))
  ) {
    throw new Error("fallback receipt route contradicts its state");
  }
  return route as unknown as FallbackReceiptRoute;
}

function validateFallbackReceiptChain(value: unknown): FallbackReceiptChain {
  const chain = record(value);
  exactKeys(chain, [
    "chain_id",
    "manifest_sha256",
    "outcome",
    "routes",
    "created_at",
  ]);
  if (
    !nonEmpty(chain.chain_id) ||
    typeof chain.manifest_sha256 !== "string" ||
    !SHA256.test(chain.manifest_sha256) ||
    !CHAIN_OUTCOMES.has(chain.outcome as string) ||
    !Array.isArray(chain.routes) ||
    chain.routes.length < 1 ||
    chain.routes.length > 16 ||
    !nonEmpty(chain.created_at)
  ) {
    throw new Error("fallback receipt chain is invalid");
  }
  const routes = chain.routes.map(validateFallbackReceiptRoute);
  if (
    new Set(routes.map((route) => `${route.provider}\0${route.model}`)).size !==
    routes.length
  ) {
    throw new Error("fallback receipt routes are not unique");
  }
  const states = routes.map((route) => route.state);
  const expected = states.every((state) => state === "unattempted")
    ? "unattempted"
    : states.includes("settled")
      ? "settled"
      : states.some(
            (state) => state === "dispatch_possible" || state === "unknown",
          )
        ? "ambiguous"
        : states.every((state) => state === "released")
          ? "exhausted"
          : "in_progress";
  if (chain.outcome !== expected) {
    throw new Error("fallback receipt chain contradicts its routes");
  }
  return { ...(chain as unknown as FallbackReceiptChain), routes };
}

function validateFallbackReceiptHistory(
  value: unknown,
): FallbackReceiptHistoryResponse {
  const body = record(value);
  exactKeys(body, ["authority", "items", "next_cursor"]);
  if (
    body.authority !== "read_only_fallback_receipt_history" ||
    !Array.isArray(body.items) ||
    body.items.length > 50 ||
    !(body.next_cursor === null || nonEmpty(body.next_cursor))
  ) {
    throw new Error("fallback receipt history is invalid");
  }
  return {
    authority: body.authority,
    items: body.items.map(validateFallbackReceiptChain),
    next_cursor: body.next_cursor as string | null,
  };
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

export async function fetchFallbackReceiptHistory(
  cursor: string | null = null,
): Promise<FallbackReceiptHistoryResponse> {
  const query = new URLSearchParams({ limit: "20" });
  if (cursor !== null) query.set("cursor", cursor);
  const res = await apiFetch(`${API_BASE}/settings/fallback-receipts?${query}`);
  if (!res.ok) {
    throw new Error(`fallback receipt history API ${res.status}`);
  }
  return validateFallbackReceiptHistory(await res.json());
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
