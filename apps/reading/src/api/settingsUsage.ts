import { API_BASE, apiFetch } from "../lib/api";

// Per-key BYOT usage + balance client. Mirrors
// interfaces/research/api/byot_usage_routes.py — every endpoint is
// owner-scoped server-side; the client never sees other users' keys.

export interface KeyUsageEntry {
  api_key_id: string;
  used_cents: number;
  limit_cents: number | null;
  remaining_cents: number | null;
}

export interface UsageSnapshotResponse {
  keys: KeyUsageEntry[];
  count: number;
}

export type BalanceKind =
  | "balance_native"
  | "spend_history"
  | "quota_pct"
  | "meter_only"
  | "unavailable";

export interface KeyBalanceResponse {
  api_key_id: string;
  catalog_id: string;
  kind: BalanceKind;
  balance_usd: number | null;
  granted_usd: number | null;
  spend_usd: number | null;
  budget_usd: number | null;
  utilization: number | null;
  window_label: string | null;
  resets_at: number | null;
  note: string | null;
}

export interface SetKeyLimitResponse {
  api_key_id: string;
  limit_cents: number | null;
  used_cents: number;
  remaining_cents: number | null;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`settings API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

/** GET /settings/usage — per-key usage snapshot for the session user. */
export async function fetchSettingsUsage(): Promise<UsageSnapshotResponse> {
  const res = await apiFetch(`${API_BASE}/settings/usage`);
  return readJson<UsageSnapshotResponse>(res);
}

/** GET /settings/balance/{api_key_id} — live provider balance. The backend
 *  degrades to kind="unavailable" (with an honest note) rather than raising. */
export async function fetchKeyBalance(
  apiKeyId: string,
): Promise<KeyBalanceResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/balance/${encodeURIComponent(apiKeyId)}`,
  );
  return readJson<KeyBalanceResponse>(res);
}

/** POST /settings/usage/{api_key_id}/limit — set (or clear, with null) a
 *  key's spend cap. Returns the updated ledger row. */
export async function setKeyLimit(
  apiKeyId: string,
  limitCents: number | null,
): Promise<SetKeyLimitResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/usage/${encodeURIComponent(apiKeyId)}/limit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit_cents: limitCents }),
    },
  );
  return readJson<SetKeyLimitResponse>(res);
}
