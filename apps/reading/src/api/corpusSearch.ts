/**
 * Corpus search client (Read SPR-08 M1).
 *
 * The Library's search box (typed query OR file-drop bias) POSTs text here.
 * Backed by the NET-NEW `GET /corpus/search` endpoint, which wraps
 * `substrate.graph.search.search` with the DEFAULT (non-privileged) policy_tag
 * — so the §9.0 gate excludes restricted content from the results. A dropped
 * file is a QUERY SIGNAL (its extracted text becomes the query), NEVER ingested
 * as new corpus.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface CorpusSearchHit {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  /** The 0-based reader page this hit anchors to, or null when its section did
   * not resolve to a page marker (then `page_resolved` is false — the UI must
   * not present an unresolved anchor as an exact page). */
  page_index: number | null;
  page_resolved: boolean;
  snippet: string;
  similarity: number;
}

export interface CorpusSearchResponse {
  query: string;
  hits: CorpusSearchHit[];
  count: number;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sanitizeHit(value: unknown): CorpusSearchHit | null {
  const hit = record(value);
  if (!hit) return null;
  const chunkId = nonEmptyString(hit.chunk_id);
  const documentId = nonEmptyString(hit.document_id);
  if (!chunkId || !documentId) return null;
  const pageIndex = nonNegativeSafeInteger(hit.page_index);
  const pageResolved = hit.page_resolved === true && pageIndex !== null;
  return {
    chunk_id: chunkId,
    document_id: documentId,
    document_title:
      typeof hit.document_title === "string" && hit.document_title.trim()
        ? hit.document_title.trim()
        : null,
    page_index: pageResolved ? pageIndex : null,
    page_resolved: pageResolved,
    snippet: typeof hit.snippet === "string" ? hit.snippet.trim() : "",
    similarity: finiteNumber(hit.similarity) ?? 0,
  };
}

function safeCorpusSearchResponse(value: unknown, fallbackQuery: string): CorpusSearchResponse {
  const body = record(value);
  if (!body) {
    throw new Error("Malformed corpus search response.");
  }
  const hits = Array.isArray(body.hits)
    ? body.hits.flatMap((item) => {
        const hit = sanitizeHit(item);
        return hit ? [hit] : [];
      })
    : [];
  return {
    query: typeof body.query === "string" ? body.query : fallbackQuery,
    hits,
    count: nonNegativeSafeInteger(body.count) ?? hits.length,
  };
}

/** Search the owned corpus by a natural-language query. `documentId` optionally
 * scopes to one document. Returns 503 when the embedding model isn't available
 * server-side. An empty/whitespace query returns an empty result (no request
 * burned). */
export async function corpusSearch(
  query: string,
  opts?: { limit?: number; documentId?: string },
): Promise<CorpusSearchResponse> {
  if (!query.trim()) return { query, hits: [], count: 0 };
  const params = new URLSearchParams({ q: query });
  if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts?.documentId !== undefined) params.set("document_id", opts.documentId);
  const resp = await apiFetch(`${API_BASE}/corpus/search?${params.toString()}`);
  if (resp.status === 503) throw new Error("Search is temporarily unavailable.");
  if (!resp.ok) throw new Error(`GET /corpus/search: HTTP ${resp.status}`);
  return safeCorpusSearchResponse(await resp.json(), query);
}
