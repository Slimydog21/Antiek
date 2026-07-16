import { API_BASE, apiFetch } from "../lib/api";

export interface DistillationHoldEvidence {
  fallback_index: number;
  hold_id: string;
  provider: string;
  model: string;
  state: "reserved" | "dispatch_possible" | "unknown" | "released" | "settled";
  projected_max_cents: number;
  actual_cents: number | null;
  is_current: boolean;
  evidence_requirement:
    | "ledger_proven_unsent"
    | "authoritative_provider_lookup"
    | "terminal_no_action";
}

export interface DistillationReconciliation {
  request_event_id: string;
  command_state: string;
  spend_run_id: string;
  fallback_chain_id: string;
  manifest_sha256: string;
  current_fallback_index: number;
  current_hold_id: string;
  currency: "USD";
  ceiling_cents: number;
  authorized_spent_cents: number;
  held_cents: number;
  available_cents: number;
  next_action: "release_proven_unsent" | "provider_lookup_required" | "none";
  action_executable: false;
  holds: DistillationHoldEvidence[];
}

export interface ReservedReleaseTerms {
  expected_command_state: "ambiguous";
  expected_spend_run_id: string;
  expected_fallback_chain_id: string;
  expected_manifest_sha256: string;
  expected_fallback_index: number;
  expected_hold_id: string;
  expected_hold_state: "reserved";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseResponse(value: unknown): DistillationReconciliation {
  if (!isRecord(value) || !Array.isArray(value.holds) || value.holds.length === 0) {
    throw new Error("Invalid reconciliation response");
  }
  const requiredStrings = [
    "request_event_id",
    "command_state",
    "spend_run_id",
    "fallback_chain_id",
    "manifest_sha256",
    "current_hold_id",
    "currency",
    "next_action",
  ] as const;
  if (requiredStrings.some((key) => typeof value[key] !== "string")) {
    throw new Error("Invalid reconciliation response");
  }
  if (
    value.currency !== "USD" ||
    value.action_executable !== false ||
    typeof value.current_fallback_index !== "number" ||
    !Number.isInteger(value.current_fallback_index) ||
    typeof value.held_cents !== "number" ||
    typeof value.available_cents !== "number" ||
    typeof value.manifest_sha256 !== "string" ||
    value.manifest_sha256.length !== 64
  ) {
    throw new Error("Invalid reconciliation response");
  }
  const holds = value.holds as unknown[];
  if (
    holds.some(
      (hold) =>
        !isRecord(hold) ||
        typeof hold.hold_id !== "string" ||
        typeof hold.fallback_index !== "number" ||
        typeof hold.state !== "string" ||
        typeof hold.projected_max_cents !== "number" ||
        typeof hold.is_current !== "boolean" ||
        typeof hold.evidence_requirement !== "string",
    )
  ) {
    throw new Error("Invalid reconciliation response");
  }
  return value as unknown as DistillationReconciliation;
}

async function jsonResponse(response: Response): Promise<DistillationReconciliation> {
  if (!response.ok) throw new Error("Reconciliation request failed");
  return parseResponse(await response.json());
}

export async function getDistillationReconciliation(
  requestEventId: string,
): Promise<DistillationReconciliation> {
  const response = await apiFetch(
    `${API_BASE}/research/distillation/commands/${encodeURIComponent(requestEventId)}/reconciliation`,
  );
  return jsonResponse(response);
}

export function reservedReleaseTerms(
  view: DistillationReconciliation,
): ReservedReleaseTerms {
  const current = view.holds.at(-1);
  if (
    view.command_state !== "ambiguous" ||
    view.next_action !== "release_proven_unsent" ||
    current?.state !== "reserved" ||
    current.hold_id !== view.current_hold_id ||
    current.fallback_index !== view.current_fallback_index
  ) {
    throw new Error("Reserved release is not authorized");
  }
  return {
    expected_command_state: "ambiguous",
    expected_spend_run_id: view.spend_run_id,
    expected_fallback_chain_id: view.fallback_chain_id,
    expected_manifest_sha256: view.manifest_sha256,
    expected_fallback_index: view.current_fallback_index,
    expected_hold_id: view.current_hold_id,
    expected_hold_state: "reserved",
  };
}

export async function releaseProvenUnsentHold(
  requestEventId: string,
  terms: ReservedReleaseTerms,
): Promise<DistillationReconciliation> {
  const response = await apiFetch(
    `${API_BASE}/research/distillation/commands/${encodeURIComponent(requestEventId)}/reconciliation/actions/release-proven-unsent`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(terms),
    },
  );
  return jsonResponse(response);
}
