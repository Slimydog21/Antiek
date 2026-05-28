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
  return (await resp.json()) as CorpusSearchResponse;
}
