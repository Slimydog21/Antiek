import { API_BASE, apiFetch } from "../lib/api";

export type SearchToolVendor = "youtube" | "x";

export interface ResearchToolCandidate {
  external_id: string;
  title_or_text: string;
  url: string;
  published_at: string | null;
  author: string | null;
  /** False for YouTube channels and playlists, which ingest refuses. */
  ingestable: boolean;
}

export interface ResearchToolSearchResponse {
  operation_id: string;
  vendor: SearchToolVendor;
  status: "completed" | "replayed";
  candidates: ResearchToolCandidate[];
}

export interface ResearchToolIngestResponse {
  operation_id: string;
  vendor: SearchToolVendor;
  external_id: string;
  status: "completed" | "replayed";
  ingest_status: "ingested" | "skipped";
  document_id: string;
  chunks_written: number;
  skipped_reason: string | null;
  title: string | null;
  content_class: string;
  source_tier: number;
}

const RESPONSE_KEYS = ["candidates", "operation_id", "status", "vendor"];
const CANDIDATE_KEYS = ["author", "external_id", "ingestable", "published_at", "title_or_text", "url"];
const INGEST_RESPONSE_KEYS = ["chunks_written", "content_class", "document_id", "external_id", "ingest_status", "operation_id", "skipped_reason", "source_tier", "status", "title", "vendor"];

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
      !nullableString(value.published_at, 64) || !nullableString(value.author, 512) ||
      typeof value.ingestable !== "boolean") {
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

function parseIngest(value: unknown): ResearchToolIngestResponse {
  if (!record(value) || !exactKeys(value, INGEST_RESPONSE_KEYS) ||
      typeof value.operation_id !== "string" || !/^[A-Za-z0-9_-]{16,128}$/.test(value.operation_id) ||
      (value.vendor !== "youtube" && value.vendor !== "x") ||
      typeof value.external_id !== "string" ||
      (value.status !== "completed" && value.status !== "replayed") ||
      (value.ingest_status !== "ingested" && value.ingest_status !== "skipped") ||
      typeof value.document_id !== "string" ||
      typeof value.chunks_written !== "number" || !Number.isInteger(value.chunks_written) || value.chunks_written < 0 ||
      !nullableString(value.skipped_reason, Infinity) || !nullableString(value.title, Infinity) ||
      typeof value.content_class !== "string" ||
      typeof value.source_tier !== "number" || !Number.isInteger(value.source_tier) || value.source_tier < 1 || value.source_tier > 5) {
    throw new Error("Tool ingest returned an invalid response");
  }
  return {
    operation_id: value.operation_id,
    vendor: value.vendor,
    external_id: value.external_id,
    status: value.status,
    ingest_status: value.ingest_status,
    document_id: value.document_id,
    chunks_written: value.chunks_written,
    skipped_reason: value.skipped_reason,
    title: value.title,
    content_class: value.content_class,
    source_tier: value.source_tier,
  };
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

export async function ingestResearchToolCandidate(input: {
  operationId: string;
  vendor: SearchToolVendor;
  externalId: string;
}): Promise<ResearchToolIngestResponse> {
  const response = await apiFetch(`${API_BASE}/research/tools/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operation_id: input.operationId, vendor: input.vendor, external_id: input.externalId }),
  });
  if (!response.ok) {
    if (response.status === 409) throw new ResearchToolIngestUnknownError();
    if (response.status === 429) throw new Error("This provider's allowance is exhausted. Try again later.");
    if (response.status === 404) throw new Error("The provider no longer has this item.");
    throw new Error("Can't ingest this candidate. Check the connected tool in Settings.");
  }
  const result = parseIngest(await response.json());
  if (result.operation_id !== input.operationId || result.vendor !== input.vendor || result.external_id !== input.externalId) {
    throw new Error("Tool ingest returned an invalid response");
  }
  return result;
}

export class ResearchToolIngestUnknownError extends Error {
  constructor() { super("This ingest has an unresolved outcome. Check your library before trying again."); }
}
