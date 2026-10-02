import { apiFetch } from "../lib/api";
import type { UserModelChoice } from "../lib/api";

export interface QuickAskInput {
  question: string;
  operation_id: string;
  model_choice: UserModelChoice;
}

export interface QuickAskModel {
  provider_id: string;
  model_id: string;
  display_name: string;
  price_snapshot: string;
  price_source: string;
}

export interface QuickAskQuote {
  quote_digest: string;
  estimate_usd: string;
  reserved_cents: number;
  price_snapshot: string;
  price_source: string;
  provider_id: string;
  model_id: string;
  max_output_tokens: number;
  warning: string;
}

export type QuickAskUsageBasis =
  | "provider_reported_tokens_priced_locally"
  | "prior_receipt"
  | "charge_unknown";

export interface QuickAskResult {
  answer: string;
  operation_id: string;
  provider_id: string;
  model_id: string;
  estimated_cost_usd: number | null;
  usage_basis: QuickAskUsageBasis;
  input_tokens: number | null;
  output_tokens: number | null;
  replayed: boolean;
  incomplete: boolean;
  reported_usage_estimate_exceeds_quote: boolean | null;
}

export type QuickAskRecentOperation =
  | { status: "answered"; operation_id: string; created_at: string; result: QuickAskResult }
  | { status: "charge_unknown"; operation_id: string; created_at: string; result: null };

export type QuickAskFailure =
  | "signed_owner_required"
  | "quick_ask_model_unavailable"
  | "quick_ask_quote_changed"
  | "quick_ask_operation_conflict"
  | "charge_unknown"
  | "quick_ask_request_invalid"
  | "quick_ask_json_required"
  | "quick_ask_models_unavailable"
  | "quick_ask_unavailable";

export class QuickAskError extends Error {
  constructor(public readonly reason: QuickAskFailure) {
    super(reason);
  }
}

const knownFailures = new Set<QuickAskFailure>([
  "signed_owner_required", "quick_ask_model_unavailable", "quick_ask_quote_changed",
  "quick_ask_operation_conflict", "charge_unknown", "quick_ask_request_invalid",
  "quick_ask_json_required", "quick_ask_models_unavailable", "quick_ask_unavailable",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function nonnegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function usdEstimate(value: unknown): value is string {
  // Decimal can emit exponent notation; retain the server's exact string.
  return typeof value === "string" && value.length <= 80 &&
    /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) &&
    nonnegative(Number(value));
}

function nullableCount(value: unknown): value is number | null {
  return value === null || (Number.isInteger(value) && nonnegative(value));
}

function operationId(value: unknown): value is string {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" &&
    /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

function parseQuote(value: unknown): QuickAskQuote {
  if (!isRecord(value) ||
      typeof value.quote_digest !== "string" || !/^[0-9a-f]{64}$/.test(value.quote_digest) ||
      !usdEstimate(value.estimate_usd) ||
      !Number.isInteger(value.reserved_cents) || !nonnegative(value.reserved_cents) ||
      !nonempty(value.price_snapshot) || !nonempty(value.price_source) ||
      !nonempty(value.provider_id) || !nonempty(value.model_id) ||
      !Number.isInteger(value.max_output_tokens) || !nonnegative(value.max_output_tokens) ||
      value.max_output_tokens === 0 || !nonempty(value.warning)) {
    throw new QuickAskError("quick_ask_unavailable");
  }
  return {
    quote_digest: value.quote_digest,
    estimate_usd: value.estimate_usd,
    reserved_cents: value.reserved_cents,
    price_snapshot: value.price_snapshot,
    price_source: value.price_source,
    provider_id: value.provider_id,
    model_id: value.model_id,
    max_output_tokens: value.max_output_tokens,
    warning: value.warning,
  };
}

function parseResult(value: unknown): QuickAskResult {
  const basis = isRecord(value) ? value.usage_basis : null;
  if (!isRecord(value) ||
      typeof value.answer !== "string" || !nonempty(value.operation_id) ||
      !nonempty(value.provider_id) || !nonempty(value.model_id) ||
      (value.estimated_cost_usd !== null && !nonnegative(value.estimated_cost_usd)) ||
      (basis !== "provider_reported_tokens_priced_locally" &&
        basis !== "prior_receipt" && basis !== "charge_unknown") ||
      !nullableCount(value.input_tokens) || !nullableCount(value.output_tokens) ||
      typeof value.replayed !== "boolean" || typeof value.incomplete !== "boolean" ||
      (value.reported_usage_estimate_exceeds_quote !== null &&
        typeof value.reported_usage_estimate_exceeds_quote !== "boolean")) {
    throw new QuickAskError("charge_unknown");
  }
  if (
    (basis === "charge_unknown" &&
      (value.estimated_cost_usd !== null || value.input_tokens !== null ||
       value.output_tokens !== null || value.reported_usage_estimate_exceeds_quote !== null)) ||
    (basis === "prior_receipt" &&
      (!value.replayed || value.estimated_cost_usd === null ||
       value.input_tokens !== null || value.output_tokens !== null)) ||
    (basis === "provider_reported_tokens_priced_locally" &&
      (value.replayed || value.estimated_cost_usd === null ||
       value.input_tokens === null || value.output_tokens === null))
  ) {
    throw new QuickAskError("charge_unknown");
  }
  return {
    answer: value.answer,
    operation_id: value.operation_id,
    provider_id: value.provider_id,
    model_id: value.model_id,
    estimated_cost_usd: value.estimated_cost_usd,
    usage_basis: basis,
    input_tokens: value.input_tokens,
    output_tokens: value.output_tokens,
    replayed: value.replayed,
    incomplete: value.incomplete,
    reported_usage_estimate_exceeds_quote: value.reported_usage_estimate_exceeds_quote,
  };
}

async function parseError(response: Response, fallback: QuickAskFailure): Promise<QuickAskError> {
  try {
    const value: unknown = await response.json();
    if (isRecord(value) && typeof value.detail === "string" &&
        knownFailures.has(value.detail as QuickAskFailure)) {
      return new QuickAskError(value.detail as QuickAskFailure);
    }
  } catch {
    // Upstream text can include provider details or a prompt; never surface it.
  }
  return new QuickAskError(fallback);
}

export async function fetchQuickAskModels(): Promise<QuickAskModel[]> {
  let response: Response;
  try {
    response = await apiFetch("/research/quick-ask/models");
  } catch {
    throw new QuickAskError("quick_ask_models_unavailable");
  }
  if (!response.ok) throw await parseError(response, "quick_ask_models_unavailable");
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new QuickAskError("quick_ask_models_unavailable");
  }
  if (!isRecord(value) || !Array.isArray(value.models) ||
      !Number.isInteger(value.count) || value.count !== value.models.length ||
      !value.models.every((model: unknown) => isRecord(model) &&
        nonempty(model.provider_id) && nonempty(model.model_id) &&
        nonempty(model.display_name) && nonempty(model.price_snapshot) &&
        nonempty(model.price_source))) {
    throw new QuickAskError("quick_ask_models_unavailable");
  }
  return value.models as QuickAskModel[];
}

export async function fetchQuickAskRecent(): Promise<QuickAskRecentOperation[]> {
  let response: Response;
  try {
    response = await apiFetch("/research/quick-ask/recent", { cache: "no-store" });
  } catch {
    throw new QuickAskError("quick_ask_unavailable");
  }
  if (!response.ok) throw await parseError(response, "quick_ask_unavailable");
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new QuickAskError("quick_ask_unavailable");
  }
  if (!isRecord(value) || !Array.isArray(value.operations) || value.operations.length > 10) {
    throw new QuickAskError("quick_ask_unavailable");
  }
  const rawOperations: unknown[] = value.operations;
  const operations: QuickAskRecentOperation[] = [];
  const seen = new Set<string>();
  try {
    for (const row of rawOperations) {
      if (!isRecord(row) || !operationId(row.operation_id) ||
          !timestamp(row.created_at) || seen.has(row.operation_id)) {
        throw new QuickAskError("quick_ask_unavailable");
      }
      seen.add(row.operation_id);
      if (row.status === "charge_unknown" && row.result === null) {
        operations.push({
          status: "charge_unknown", operation_id: row.operation_id,
          created_at: row.created_at, result: null,
        });
      } else if (row.status === "answered") {
        const result = parseResult(row.result);
        if (result.operation_id !== row.operation_id || !result.replayed ||
            (result.usage_basis !== "prior_receipt" && result.usage_basis !== "charge_unknown")) {
          throw new QuickAskError("quick_ask_unavailable");
        }
        operations.push({
          status: "answered", operation_id: row.operation_id,
          created_at: row.created_at, result,
        });
      } else {
        throw new QuickAskError("quick_ask_unavailable");
      }
    }
  } catch {
    throw new QuickAskError("quick_ask_unavailable");
  }
  return operations;
}

export async function quoteQuickAsk(input: QuickAskInput): Promise<QuickAskQuote> {
  let response: Response;
  try {
    response = await apiFetch("/research/quick-ask/quote", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  } catch {
    throw new QuickAskError("quick_ask_unavailable");
  }
  if (!response.ok) throw await parseError(response, "quick_ask_unavailable");
  const value: unknown = await response.json();
  const quote = parseQuote(value);
  if (quote.provider_id !== input.model_choice.provider_id) {
    throw new QuickAskError("quick_ask_unavailable");
  }
  return quote;
}

export async function sendQuickAsk(
  input: QuickAskInput,
  quote: QuickAskQuote,
): Promise<QuickAskResult> {
  if (quote.provider_id !== input.model_choice.provider_id) {
    throw new QuickAskError("quick_ask_model_unavailable");
  }
  let response: Response;
  try {
    response = await apiFetch("/research/quick-ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...input, quote_digest: quote.quote_digest }),
    });
  } catch {
    // A browser transport error cannot tell whether the server sent the paid
    // request. Keep the operation ID and require a deliberate provider check.
    throw new QuickAskError("charge_unknown");
  }
  if (!response.ok) throw await parseError(response, "charge_unknown");
  try {
    const value: unknown = await response.json();
    const result = parseResult(value);
    if (result.operation_id !== input.operation_id ||
        result.provider_id !== quote.provider_id ||
        result.model_id !== quote.model_id) {
      throw new QuickAskError("charge_unknown");
    }
    return result;
  } catch {
    throw new QuickAskError("charge_unknown");
  }
}
