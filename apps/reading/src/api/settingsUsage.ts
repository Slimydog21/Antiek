import { API_BASE, apiFetch } from "../lib/api";

export interface SettingsUsageKeyEntry {
  api_key_id: string;
  used_cents: number;
  limit_cents: number | null;
  remaining_cents: number | null;
  held_cents: number;
  available_cents: number | null;
}

export interface SettingsUsageSnapshotResponse {
  keys: SettingsUsageKeyEntry[];
  count: number;
}

export interface SettingsUsageLimitRequest {
  limit_cents: number | null;
}

export interface SettingsUsageLimitResponse {
  api_key_id: string;
  limit_cents: number | null;
  used_cents: number;
  remaining_cents: number | null;
  held_cents: number;
  available_cents: number | null;
}

export type SettingsBalanceKind =
  | "balance_native"
  | "spend_history"
  | "quota_pct"
  | "meter_only"
  | "unavailable";

export interface SettingsNativeBalance {
  currency: string;
  total: string;
  granted: string;
  topped_up: string;
}

export interface SettingsBalanceResponse {
  api_key_id: string;
  catalog_id: string;
  kind: SettingsBalanceKind;
  balance_usd: number | null;
  granted_usd: number | null;
  spend_usd: number | null;
  budget_usd: number | null;
  utilization: number | null;
  window_label: string | null;
  resets_at: number | null;
  note: string | null;
  held_cents: number;
  available_cents: number | null;
  native_balances: SettingsNativeBalance[] | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function isSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value);
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isDecimalString(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 &&
    /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(value);
}

function parseNativeBalances(raw: unknown): SettingsNativeBalance[] | null {
  if (raw === null) return null;
  if (!Array.isArray(raw) || raw.length > 8) {
    throw new Error("Invalid settings balance response.");
  }
  const currencies = new Set<string>();
  return raw.map((entry: unknown) => {
    if (
      !isRecord(entry) ||
      !hasExactKeys(entry, ["currency", "total", "granted", "topped_up"]) ||
      typeof entry.currency !== "string" ||
      !/^[A-Z]{3}$/.test(entry.currency) ||
      currencies.has(entry.currency) ||
      !isDecimalString(entry.total) ||
      !isDecimalString(entry.granted) ||
      !isDecimalString(entry.topped_up)
    ) {
      throw new Error("Invalid settings balance response.");
    }
    currencies.add(entry.currency);
    return {
      currency: entry.currency,
      total: entry.total,
      granted: entry.granted,
      topped_up: entry.topped_up,
    };
  });
}

function parseUsageEntry(raw: unknown): SettingsUsageKeyEntry {
  if (
    !isRecord(raw) ||
    !hasExactKeys(raw, [
      "api_key_id",
      "used_cents",
      "limit_cents",
      "remaining_cents",
      "held_cents",
      "available_cents",
    ]) ||
    typeof raw.api_key_id !== "string" ||
    raw.api_key_id.length === 0 ||
    !isSafeInteger(raw.used_cents) ||
    raw.used_cents < 0 ||
    !(raw.limit_cents === null || (isSafeInteger(raw.limit_cents) && raw.limit_cents >= 0)) ||
    !(raw.remaining_cents === null || isSafeInteger(raw.remaining_cents)) ||
    !isSafeInteger(raw.held_cents) ||
    raw.held_cents < 0 ||
    !(raw.available_cents === null || isSafeInteger(raw.available_cents))
  ) {
    throw new Error("Invalid settings usage response.");
  }
  return {
    api_key_id: raw.api_key_id,
    used_cents: raw.used_cents,
    limit_cents: raw.limit_cents,
    remaining_cents: raw.remaining_cents,
    held_cents: raw.held_cents,
    available_cents: raw.available_cents,
  };
}

export function parseSettingsUsageSnapshot(
  raw: unknown,
): SettingsUsageSnapshotResponse {
  if (
    !isRecord(raw) ||
    !hasExactKeys(raw, ["keys", "count"]) ||
    !Array.isArray(raw.keys)
  ) {
    throw new Error("Invalid settings usage response.");
  }
  const keys = raw.keys.map((entry) => parseUsageEntry(entry));
  if (!isSafeInteger(raw.count) || raw.count !== keys.length) {
    throw new Error("Invalid settings usage response.");
  }
  return { keys, count: raw.count };
}

export function parseSettingsUsageLimit(
  raw: unknown,
): SettingsUsageLimitResponse {
  const parsed = parseUsageEntry(raw);
  return {
    api_key_id: parsed.api_key_id,
    used_cents: parsed.used_cents,
    limit_cents: parsed.limit_cents,
    remaining_cents: parsed.remaining_cents,
    held_cents: parsed.held_cents,
    available_cents: parsed.available_cents,
  };
}

export function parseSettingsBalance(raw: unknown): SettingsBalanceResponse {
  const keys = [
    "api_key_id", "catalog_id", "kind", "balance_usd", "granted_usd",
    "spend_usd", "budget_usd", "utilization", "window_label", "resets_at",
    "note", "held_cents", "available_cents",
  ];
  if (
    !isRecord(raw) ||
    !(hasExactKeys(raw, keys) || hasExactKeys(raw, [...keys, "native_balances"])) ||
    typeof raw.api_key_id !== "string" ||
    raw.api_key_id.length === 0 ||
    typeof raw.catalog_id !== "string" ||
    raw.catalog_id.length === 0 ||
    ![
      "balance_native",
      "spend_history",
      "quota_pct",
      "meter_only",
      "unavailable",
    ].includes(String(raw.kind)) ||
    !isNullableFiniteNumber(raw.balance_usd) ||
    !isNullableFiniteNumber(raw.granted_usd) ||
    !isNullableFiniteNumber(raw.spend_usd) ||
    !isNullableFiniteNumber(raw.budget_usd) ||
    !isNullableFiniteNumber(raw.utilization) ||
    !(raw.window_label === null || typeof raw.window_label === "string") ||
    !(raw.resets_at === null || isSafeInteger(raw.resets_at)) ||
    !(raw.note === null || typeof raw.note === "string") ||
    !isSafeInteger(raw.held_cents) ||
    raw.held_cents < 0 ||
    !(raw.available_cents === null || isSafeInteger(raw.available_cents))
  ) {
    throw new Error("Invalid settings balance response.");
  }
  const nativeBalances = "native_balances" in raw
    ? parseNativeBalances(raw.native_balances)
    : null;
  if (raw.catalog_id === "deepseek" && nativeBalances !== null &&
      (raw.balance_usd !== null || raw.granted_usd !== null)) {
    throw new Error("Invalid settings balance response.");
  }
  if (raw.catalog_id === "deepseek" && raw.kind === "balance_native" &&
      nativeBalances !== null && nativeBalances.length === 0) {
    throw new Error("Invalid settings balance response.");
  }
  return {
    api_key_id: raw.api_key_id,
    catalog_id: raw.catalog_id,
    kind: raw.kind as SettingsBalanceKind,
    balance_usd: raw.catalog_id === "deepseek" ? null : raw.balance_usd,
    granted_usd: raw.catalog_id === "deepseek" ? null : raw.granted_usd,
    spend_usd: raw.spend_usd,
    budget_usd: raw.budget_usd,
    utilization: raw.utilization,
    window_label: raw.window_label,
    resets_at: raw.resets_at,
    note: raw.note,
    held_cents: raw.held_cents,
    available_cents: raw.available_cents,
    native_balances: nativeBalances,
  };
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(
      `Settings usage request failed (${res.status}). Check the values and try again.`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchSettingsUsage(): Promise<SettingsUsageSnapshotResponse> {
  const res = await apiFetch(`${API_BASE}/settings/usage`);
  return parseSettingsUsageSnapshot(await readJson<unknown>(res));
}

export async function setSettingsUsageLimit(
  apiKeyId: string,
  body: SettingsUsageLimitRequest,
): Promise<SettingsUsageLimitResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/usage/${encodeURIComponent(apiKeyId)}/limit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return parseSettingsUsageLimit(await readJson<unknown>(res));
}

export async function fetchSettingsBalance(
  apiKeyId: string,
): Promise<SettingsBalanceResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/balance/${encodeURIComponent(apiKeyId)}`,
  );
  return parseSettingsBalance(await readJson<unknown>(res));
}
