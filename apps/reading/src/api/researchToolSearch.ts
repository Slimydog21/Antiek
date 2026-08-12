import { API_BASE, apiFetch } from "../lib/api";

export type SearchToolVendor = "youtube" | "x";

export interface ResearchToolCandidate {
  external_id: string;
  title_or_text: string;
  url: string;
  published_at: string | null;
  author: string | null;
}

export interface ResearchToolSearchResponse {
  operation_id: string;
  vendor: SearchToolVendor;
  status: "completed" | "replayed";
  candidates: ResearchToolCandidate[];
}

const RESPONSE_KEYS = ["candidates", "operation_id", "status", "vendor"];
const CANDIDATE_KEYS = ["author", "external_id", "published_at", "title_or_text", "url"];

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const actual = Object.keys(value).sort();
  const sorted = [...expected].sort();
  return actual.length === sorted.length && actual.every((key, index) => key === sorted[index]);
}

function nullableString(value: unknown, max: number): value is string | null {
  return value === null || (typeof value === "string" && value.length <= max);
}

function validTimestamp(value: string | null): boolean {
  return value === null || (!Number.isNaN(Date.parse(value)) && /^\d{4}-\d{2}-\d{2}T/.test(value));
}

function candidate(value: unknown): ResearchToolCandidate {
  if (!record(value) || !exactKeys(value, CANDIDATE_KEYS) ||
      typeof value.external_id !== "string" || value.external_id.length === 0 || value.external_id.length > 256 ||
      typeof value.title_or_text !== "string" || value.title_or_text.length > 4_000 ||
      typeof value.url !== "string" || value.url.length > 2_048 ||
      !nullableString(value.published_at, 64) || !nullableString(value.author, 512)) {
    throw new Error("Tool search returned an invalid response");
  }
  let parsed: URL;
  try { parsed = new URL(value.url); } catch { throw new Error("Tool search returned an invalid response"); }
  if (parsed.protocol !== "https:" || !validTimestamp(value.published_at as string | null)) throw new Error("Tool search returned an invalid response");
  return value as unknown as ResearchToolCandidate;
}

function parse(value: unknown): ResearchToolSearchResponse {
  if (!record(value) || !exactKeys(value, RESPONSE_KEYS) ||
      typeof value.operation_id !== "string" || !/^[A-Za-z0-9_-]{16,128}$/.test(value.operation_id) ||
      (value.vendor !== "youtube" && value.vendor !== "x") ||
      (value.status !== "completed" && value.status !== "replayed") ||
      !Array.isArray(value.candidates) || value.candidates.length > 25) {
    throw new Error("Tool search returned an invalid response");
  }
  return { ...value, candidates: value.candidates.map(candidate) } as ResearchToolSearchResponse;
}

export async function searchResearchTool(input: {
  operationId: string;
  vendor: SearchToolVendor;
  query: string;
  maxResults?: number;
}): Promise<ResearchToolSearchResponse> {
  const response = await apiFetch(`${API_BASE}/research/tools/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operation_id: input.operationId,
      vendor: input.vendor,
      query: input.query,
      max_results: input.maxResults ?? 10,
    }),
  });
  if (!response.ok) {
    if (response.status === 409) throw new ResearchToolSearchUnknownError();
    if (response.status === 429) throw new Error("This provider's search allowance is exhausted.");
    throw new Error("Can't search this provider. Check the connected tool in Settings.");
  }
  return parse(await response.json());
}

export class ResearchToolSearchUnknownError extends Error {
  constructor() { super("This search has an unresolved provider outcome. Check provider usage before starting another search."); }
}
