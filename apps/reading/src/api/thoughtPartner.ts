export interface ThoughtPartnerModelReceipt {
  authority: "owner_byot";
  requested_provider_id: string;
  requested_model_id: string;
  actual_provider_id: string;
  actual_model_id: string;
  authority_digest: string;
}

export interface ThoughtPartnerSemanticRequest {
  prompt: string;
  history: readonly unknown[];
  system_context: string;
  investigation_id?: string;
}

export interface ThoughtPartnerReceiptDisplay {
  receipt: ThoughtPartnerModelReceipt;
  requestedDisplayName: string | null;
}

/** Stable launch identity input. Keep every field that can change the answer. */
export function thoughtPartnerLaunchKey(
  request: ThoughtPartnerSemanticRequest,
): string {
  return JSON.stringify({
    prompt: request.prompt,
    history: request.history,
    system_context: request.system_context,
    investigation_id: request.investigation_id ?? null,
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function thoughtPartnerReceiptLabel(
  display: ThoughtPartnerReceiptDisplay,
): string {
  const friendlyName = display.requestedDisplayName?.trim();
  return friendlyName && friendlyName !== display.receipt.actual_model_id
    ? `${friendlyName} · ${display.receipt.actual_model_id}`
    : display.receipt.actual_model_id;
}

function failureCode(value: unknown): string | null {
  if (!isRecord(value)) return null;
  if (typeof value.detail === "string") return value.detail;
  if (isRecord(value.detail) && typeof value.detail.code === "string") {
    return value.detail.code;
  }
  if (typeof value.code === "string") return value.code;
  return null;
}

export async function thoughtPartnerFailureMessage(
  response: Pick<Response, "status" | "json">,
  selectedModelLabel: string | null,
): Promise<string> {
  let code: string | null = null;
  try {
    code = failureCode(await response.json());
  } catch {
    // Preserve the existing status-only error when the body is absent or invalid.
  }
  if (code === "owner_model_outcome_unknown") {
    return "The provider response could not be confirmed. Check usage before starting another turn.";
  }
  if (code === "owner_model_unavailable") {
    const label = selectedModelLabel?.trim() || "The selected model";
    return `${label} is unavailable. Choose another model or try again later.`;
  }
  return `Thought-partner unavailable (HTTP ${response.status}).`;
}

export function parseThoughtPartnerModelReceipt(
  value: unknown,
): ThoughtPartnerModelReceipt | null {
  if (value === null || value === undefined) return null;
  if (
    !isRecord(value) ||
    value.authority !== "owner_byot" ||
    typeof value.requested_provider_id !== "string" ||
    typeof value.requested_model_id !== "string" ||
    typeof value.actual_provider_id !== "string" ||
    typeof value.actual_model_id !== "string" ||
    typeof value.authority_digest !== "string"
  ) {
    return null;
  }
  return {
    authority: value.authority,
    requested_provider_id: value.requested_provider_id,
    requested_model_id: value.requested_model_id,
    actual_provider_id: value.actual_provider_id,
    actual_model_id: value.actual_model_id,
    authority_digest: value.authority_digest,
  };
}
