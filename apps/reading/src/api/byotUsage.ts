import { API_BASE, apiFetch } from "../lib/api";

export interface KeyUsageEntry {
  api_key_id: string;
  used_cents: number;
  limit_cents: number | null;
  remaining_cents: number | null;
}

export interface UsageSnapshot {
  keys: KeyUsageEntry[];
  count: number;
}

export type BalanceKind =
  | "balance_native"
  | "spend_history"
  | "quota_pct"
  | "meter_only"
  | "unavailable";

export interface KeyBalance {
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

const BALANCE_KINDS = new Set<BalanceKind>([
  "balance_native",
  "spend_history",
  "quota_pct",
  "meter_only",
  "unavailable",
]);
const MAX_RENDERABLE_EPOCH_SECONDS = 8_640_000_000_000;

function validKeyId(value: string): boolean {
  return value.length > 0 && value.length <= 256 && value === value.trim();
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${context} returned an invalid response`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, expected: string[], context: string) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new Error(`${context} returned an invalid response`);
  }
}

function finiteNumber(value: unknown, context: string, nullable = true): number | null {
  if (nullable && value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER) {
    throw new Error(`${context} returned an invalid response`);
  }
  return value;
}

function integer(value: unknown, context: string, nullable = true): number | null {
  const parsed = finiteNumber(value, context, nullable);
  if (parsed !== null && !Number.isSafeInteger(parsed)) {
    throw new Error(`${context} returned an invalid response`);
  }
  return parsed;
}

function textOrNull(value: unknown, context: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string") throw new Error(`${context} returned an invalid response`);
  return value;
}

function parseUsageEntry(value: unknown): KeyUsageEntry {
  const row = record(value, "usage API");
  exactKeys(row, ["api_key_id", "used_cents", "limit_cents", "remaining_cents"], "usage API");
  if (typeof row.api_key_id !== "string" || row.api_key_id.length === 0) {
    throw new Error("usage API returned an invalid response");
  }
  const used = integer(row.used_cents, "usage API", false) as number;
  const limit = integer(row.limit_cents, "usage API");
  const remaining = integer(row.remaining_cents, "usage API");
  if ((limit === null) !== (remaining === null)) {
    throw new Error("usage API returned an invalid response");
  }
  if (limit !== null && remaining !== Math.max(0, limit - used)) {
    throw new Error("usage API returned an invalid response");
  }
  return { api_key_id: row.api_key_id, used_cents: used, limit_cents: limit, remaining_cents: remaining };
}

function parseUsage(value: unknown): UsageSnapshot {
  const payload = record(value, "usage API");
  exactKeys(payload, ["keys", "count"], "usage API");
  if (!Array.isArray(payload.keys)) throw new Error("usage API returned an invalid response");
  const keys = payload.keys.map(parseUsageEntry);
  const count = integer(payload.count, "usage API", false) as number;
  if (count !== keys.length || new Set(keys.map((key) => key.api_key_id)).size !== keys.length) {
    throw new Error("usage API returned an invalid response");
  }
  if (keys.reduce((sum, key) => sum + BigInt(key.used_cents), 0n) > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("usage API returned an invalid response");
  }
  return { keys, count };
}

function parseBalance(value: unknown): KeyBalance {
  const payload = record(value, "balance API");
  exactKeys(payload, [
    "api_key_id", "catalog_id", "kind", "balance_usd", "granted_usd", "spend_usd",
    "budget_usd", "utilization", "window_label", "resets_at", "note",
  ], "balance API");
  if (typeof payload.api_key_id !== "string" || payload.api_key_id.length === 0 ||
      typeof payload.catalog_id !== "string" || payload.catalog_id.length === 0 ||
      typeof payload.kind !== "string" || !BALANCE_KINDS.has(payload.kind as BalanceKind)) {
    throw new Error("balance API returned an invalid response");
  }
  const utilization = finiteNumber(payload.utilization, "balance API");
  if (utilization !== null && utilization > 1) throw new Error("balance API returned an invalid response");
  const resetsAt = integer(payload.resets_at, "balance API");
  if (resetsAt !== null && resetsAt > MAX_RENDERABLE_EPOCH_SECONDS) {
    throw new Error("balance API returned an invalid response");
  }
  const parsed: KeyBalance = {
    api_key_id: payload.api_key_id,
    catalog_id: payload.catalog_id,
    kind: payload.kind as BalanceKind,
    balance_usd: finiteNumber(payload.balance_usd, "balance API"),
    granted_usd: finiteNumber(payload.granted_usd, "balance API"),
    spend_usd: finiteNumber(payload.spend_usd, "balance API"),
    budget_usd: finiteNumber(payload.budget_usd, "balance API"),
    utilization,
    window_label: textOrNull(payload.window_label, "balance API"),
    resets_at: resetsAt,
    note: textOrNull(payload.note, "balance API"),
  };
  const noNative = parsed.balance_usd === null && parsed.granted_usd === null;
  const noSpend = parsed.spend_usd === null && parsed.budget_usd === null;
  const noQuota = parsed.utilization === null && parsed.window_label === null && parsed.resets_at === null;
  if (parsed.kind === "balance_native" &&
      (parsed.balance_usd === null || !noSpend || !noQuota)) {
    throw new Error("balance API returned an invalid response");
  }
  if (parsed.kind === "spend_history" &&
      (parsed.spend_usd === null || !noNative || !noQuota)) {
    throw new Error("balance API returned an invalid response");
  }
  if (parsed.kind === "quota_pct" &&
      (parsed.utilization === null || !parsed.window_label?.trim() || !noNative || !noSpend)) {
    throw new Error("balance API returned an invalid response");
  }
  if (parsed.kind === "meter_only" &&
      (parsed.spend_usd === null || !noNative || parsed.budget_usd !== null || parsed.utilization !== null)) {
    throw new Error("balance API returned an invalid response");
  }
  if (parsed.kind === "unavailable" && (!noNative || !noSpend || !noQuota)) {
    throw new Error("balance API returned an invalid response");
  }
  return parsed;
}

async function json(res: Response, context: string): Promise<unknown> {
  if (!res.ok) throw new Error(`${context} ${res.status}`);
  try {
    return await res.json();
  } catch {
    throw new Error(`${context} returned an invalid response`);
  }
}

export async function fetchUsageSnapshot(): Promise<UsageSnapshot> {
  const res = await apiFetch(`${API_BASE}/settings/usage`);
  return parseUsage(await json(res, "usage API"));
}

export async function fetchKeyBalance(apiKeyId: string): Promise<KeyBalance> {
  if (!validKeyId(apiKeyId)) throw new Error("balance API request is invalid");
  const res = await apiFetch(`${API_BASE}/settings/balance/${encodeURIComponent(apiKeyId)}`);
  const balance = parseBalance(await json(res, "balance API"));
  if (balance.api_key_id !== apiKeyId) throw new Error("balance API returned an invalid response");
  return balance;
}

export async function setKeyLimit(apiKeyId: string, limitCents: number | null): Promise<KeyUsageEntry> {
  if (!validKeyId(apiKeyId) ||
      (limitCents !== null && (!Number.isSafeInteger(limitCents) || limitCents < 0))) {
    throw new Error("usage API request is invalid");
  }
  const res = await apiFetch(`${API_BASE}/settings/usage/${encodeURIComponent(apiKeyId)}/limit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit_cents: limitCents }),
  });
  const entry = parseUsageEntry(await json(res, "usage API"));
  if (entry.api_key_id !== apiKeyId) throw new Error("usage API returned an invalid response");
  return entry;
}
