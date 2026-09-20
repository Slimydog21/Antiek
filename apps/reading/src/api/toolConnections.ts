import { API_BASE, apiFetch } from "../lib/api";

export type ToolVendor = "youtube" | "x" | "polygon" | "fmp" | "edgar";
export type ToolConnectionStatus =
  | "unconfigured"
  | "configured_unverified"
  | "degraded";

export interface ToolQuota {
  kind: "youtube_units" | "rate_ceiling" | "unavailable";
  remaining: number | null;
  limit: number | null;
  reset_at: string | null;
  hard_exhausted: boolean | null;
  note: string | null;
}

export interface ToolConnection {
  vendor: ToolVendor;
  display_name: string;
  credential_kind: "api_key" | "contact";
  auth: string;
  docs_url: string;
  status: ToolConnectionStatus;
  credential_present: boolean;
  status_note: string | null;
  quota: ToolQuota;
}

const VENDORS = new Set<ToolVendor>(["youtube", "x", "polygon", "fmp", "edgar"]);
const STATUSES = new Set<ToolConnectionStatus>([
  "unconfigured",
  "configured_unverified",
  "degraded",
]);
const QUOTA_KINDS = new Set<ToolQuota["kind"]>([
  "youtube_units",
  "rate_ceiling",
  "unavailable",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, i) => key === [...expected].sort()[i]);
}

function parseQuota(value: unknown): ToolQuota {
  if (!isRecord(value) || !exactKeys(value, [
    "hard_exhausted", "kind", "limit", "note", "remaining", "reset_at",
  ])) throw new Error("Tool settings returned an invalid quota response");
  if (typeof value.kind !== "string" || !QUOTA_KINDS.has(value.kind as ToolQuota["kind"])) {
    throw new Error("Tool settings returned an invalid quota response");
  }
  const nullableNumber = (candidate: unknown) =>
    candidate === null ||
    (typeof candidate === "number" && Number.isFinite(candidate) && candidate >= 0);
  const nullableString = (candidate: unknown) => candidate === null || typeof candidate === "string";
  if (!nullableNumber(value.remaining) || !nullableNumber(value.limit) ||
      !nullableString(value.reset_at) || !nullableString(value.note) ||
      !(value.hard_exhausted === null || typeof value.hard_exhausted === "boolean")) {
    throw new Error("Tool settings returned an invalid quota response");
  }
  const remaining = value.remaining as number | null;
  const limit = value.limit as number | null;
  const resetAt = value.reset_at as string | null;
  const hardExhausted = value.hard_exhausted as boolean | null;
  if (
    (remaining !== null && limit !== null && remaining > limit) ||
    (resetAt !== null && Number.isNaN(Date.parse(resetAt))) ||
    (value.kind === "youtube_units" &&
      hardExhausted === true && remaining !== 0) ||
    (value.kind !== "youtube_units" &&
      (remaining !== null || resetAt !== null || hardExhausted !== null)) ||
    (value.kind === "youtube_units" && limit !== null && limit <= 0) ||
    (value.kind === "rate_ceiling" && (limit === null || limit <= 0)) ||
    (value.kind === "unavailable" && limit !== null)
  ) {
    throw new Error("Tool settings returned an invalid quota response");
  }
  return value as unknown as ToolQuota;
}

function parseConnection(value: unknown): ToolConnection {
  if (!isRecord(value) || !exactKeys(value, [
    "auth", "credential_kind", "credential_present", "display_name", "docs_url",
    "quota", "status", "status_note", "vendor",
  ])) throw new Error("Tool settings returned an invalid connection response");
  if (typeof value.vendor !== "string" || !VENDORS.has(value.vendor as ToolVendor) ||
      typeof value.status !== "string" || !STATUSES.has(value.status as ToolConnectionStatus) ||
      (value.credential_kind !== "api_key" && value.credential_kind !== "contact") ||
      typeof value.display_name !== "string" || typeof value.auth !== "string" ||
      typeof value.docs_url !== "string" || typeof value.credential_present !== "boolean" ||
      !(value.status_note === null || typeof value.status_note === "string")) {
    throw new Error("Tool settings returned an invalid connection response");
  }
  let docsUrl: URL;
  try {
    docsUrl = new URL(value.docs_url);
  } catch {
    throw new Error("Tool settings returned an invalid connection response");
  }
  if (
    docsUrl.protocol !== "https:" ||
    (value.status === "unconfigured" && value.credential_present) ||
    (value.status === "configured_unverified" && !value.credential_present)
  ) {
    throw new Error("Tool settings returned an invalid connection response");
  }
  return { ...(value as unknown as Omit<ToolConnection, "quota">), quota: parseQuota(value.quota) };
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`Tool settings API ${response.status}`);
  return response.json() as Promise<unknown>;
}

export async function fetchToolConnections(): Promise<ToolConnection[]> {
  const payload = await readJson(await apiFetch(`${API_BASE}/settings/tools`));
  if (!isRecord(payload) || !exactKeys(payload, ["connections", "count"]) ||
      !Array.isArray(payload.connections) || typeof payload.count !== "number" ||
      payload.count !== payload.connections.length) {
    throw new Error("Tool settings returned an invalid inventory response");
  }
  return payload.connections.map(parseConnection);
}

export async function saveToolConnection(
  vendor: ToolVendor,
  credential: string,
): Promise<ToolConnection> {
  const response = await apiFetch(`${API_BASE}/settings/tools/${encodeURIComponent(vendor)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  return parseConnection(await readJson(response));
}

export async function removeToolConnection(vendor: ToolVendor): Promise<void> {
  const response = await apiFetch(`${API_BASE}/settings/tools/${encodeURIComponent(vendor)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`Tool settings API ${response.status}`);
}
