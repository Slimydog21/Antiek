import { API_BASE, ApiError, apiFetch } from "../lib/api";

export type DeepResearchSessionResumeRef = { session_id: string };
export type DeepResearchSessionProjection = DeepResearchSessionResumeRef & {
  schema_version: 1;
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  status: "reserved" | "running" | "complete" | "failed";
  research_tier: "fast" | "deep" | "wrestle";
  view_format: "html";
};

function identifier(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value === value.trim()
    && new TextEncoder().encode(value).length <= 512 && !/[\u0000-\u001f\u007f-\u009f]/u.test(value);
}

function exact(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const object = value as Record<string, unknown>;
  const expected = [...keys].sort();
  const actual = Object.keys(object).sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]) ? object : null;
}

export function parseDeepResearchSessionResumeRef(value: unknown): DeepResearchSessionResumeRef | null {
  const object = exact(value, ["session_id"]);
  return object && identifier(object.session_id) ? { session_id: object.session_id } : null;
}

export function parseDeepResearchSessionProjection(value: unknown): DeepResearchSessionProjection {
  const object = exact(value, ["schema_version", "session_id", "spawn_id", "investigation_id", "parent_asset_id", "status", "research_tier", "view_format"]);
  if (!object || object.schema_version !== 1 || !identifier(object.session_id) || !identifier(object.spawn_id)
    || !identifier(object.investigation_id) || !identifier(object.parent_asset_id)
    || !["reserved", "running", "complete", "failed"].includes(String(object.status))
    || !["fast", "deep", "wrestle"].includes(String(object.research_tier)) || object.view_format !== "html") {
    throw new Error("invalid deep research session reference response");
  }
  return object as DeepResearchSessionProjection;
}

export async function fetchDeepResearchSessionReference(sessionId: string, signal?: AbortSignal): Promise<DeepResearchSessionProjection> {
  if (!identifier(sessionId)) throw new Error("invalid deep research session reference");
  const response = await apiFetch(`${API_BASE}/account/deep-research-session-refs/${encodeURIComponent(sessionId)}`, { signal, cache: "no-store" });
  if (!response.ok) throw new ApiError("deep research session reference request failed", response.status, await response.text());
  return parseDeepResearchSessionProjection(await response.json());
}
