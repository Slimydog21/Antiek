import { API_BASE, apiFetch } from "../lib/api";

export type ComputeCapacityTier = "starter" | "standard" | "power" | "custom";
export type ComputeUsedStatus = "unmetered" | "known";
export type ComputeEnforcement = "off" | "soft" | "hard";

export interface ComputeCapacityEvaluation {
  allowed: boolean;
  soft_over: boolean;
  would_hard_block: boolean;
  note: string;
}

export interface ComputeCapacityResponse {
  owner_user_id: string;
  tier: ComputeCapacityTier;
  monthly_compute_units: number;
  used_compute_units: number | null;
  used_status: ComputeUsedStatus;
  enforcement: ComputeEnforcement;
  updated_at: string | null;
  is_default: boolean;
  tier_presets: Record<string, number>;
  evaluation: ComputeCapacityEvaluation;
  note: string;
}

export interface SetComputeCapacityRequest {
  tier: ComputeCapacityTier;
  monthly_compute_units?: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseCapacity(raw: unknown): ComputeCapacityResponse {
  if (!isRecord(raw)) throw new Error("invalid_compute_capacity");
  const ev = raw.evaluation;
  if (!isRecord(ev)) throw new Error("invalid_compute_capacity_evaluation");
  return {
    owner_user_id: String(raw.owner_user_id),
    tier: raw.tier as ComputeCapacityTier,
    monthly_compute_units: Number(raw.monthly_compute_units),
    used_compute_units:
      raw.used_compute_units === null || raw.used_compute_units === undefined
        ? null
        : Number(raw.used_compute_units),
    used_status: raw.used_status as ComputeUsedStatus,
    enforcement: raw.enforcement as ComputeEnforcement,
    updated_at: raw.updated_at === null ? null : String(raw.updated_at),
    is_default: Boolean(raw.is_default),
    tier_presets: (raw.tier_presets as Record<string, number>) ?? {},
    evaluation: {
      allowed: Boolean(ev.allowed),
      soft_over: Boolean(ev.soft_over),
      would_hard_block: Boolean(ev.would_hard_block),
      note: String(ev.note ?? ""),
    },
    note: String(raw.note ?? ""),
  };
}

export async function fetchComputeCapacity(): Promise<ComputeCapacityResponse> {
  const resp = await apiFetch(`${API_BASE}/settings/compute-capacity`);
  if (!resp.ok) throw new Error(`compute_capacity_get_${resp.status}`);
  return parseCapacity(await resp.json());
}

export async function setComputeCapacity(
  body: SetComputeCapacityRequest,
): Promise<ComputeCapacityResponse> {
  const resp = await apiFetch(`${API_BASE}/settings/compute-capacity`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tier: body.tier,
      monthly_compute_units: body.monthly_compute_units ?? null,
    }),
  });
  if (!resp.ok) throw new Error(`compute_capacity_put_${resp.status}`);
  return parseCapacity(await resp.json());
}
