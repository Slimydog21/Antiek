/**
 * Twin-notes search client (PR #789 contract).
 *
 * GET /twins/search?q=&parent_asset_id=&limit=
 *
 * Searches LLM twin insight/question substrate — never invents hits.
 * Empty query rejected before network.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface TwinSearchHit {
  twin_id: string;
  parent_asset_id: string;
  score: number;
  matched_insights: string[];
  matched_questions: string[];
  source_label: string | null;
}

export interface TwinSearchResponse {
  query: string;
  count: number;
  hits: TwinSearchHit[];
}

export interface TwinSearchRequest {
  q: string;
  parent_asset_id?: string | null;
  limit?: number;
}

export class TwinSearchHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`twin-search API ${status}: ${body.slice(0, 200)}`);
    this.name = "TwinSearchHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new TwinSearchHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

export function parseTwinSearchHit(raw: unknown, path = "hit"): TwinSearchHit {
  if (!raw || typeof raw !== "object") {
    throw new Error(`twin-search rejected: ${path} must be object`);
  }
  const o = raw as Record<string, unknown>;
  if (typeof o.twin_id !== "string" || !o.twin_id.trim()) {
    throw new Error(`twin-search rejected: ${path}.twin_id required`);
  }
  if (typeof o.parent_asset_id !== "string" || !o.parent_asset_id.trim()) {
    throw new Error(`twin-search rejected: ${path}.parent_asset_id required`);
  }
  if (typeof o.score !== "number" || !Number.isFinite(o.score)) {
    throw new Error(`twin-search rejected: ${path}.score must be finite number`);
  }
  if (!Array.isArray(o.matched_insights) || !Array.isArray(o.matched_questions)) {
    throw new Error(
      `twin-search rejected: ${path}.matched_insights/questions must be arrays`,
    );
  }
  return {
    twin_id: o.twin_id,
    parent_asset_id: o.parent_asset_id,
    score: o.score,
    matched_insights: o.matched_insights.map((x) => String(x)),
    matched_questions: o.matched_questions.map((x) => String(x)),
    source_label:
      o.source_label === null || o.source_label === undefined
        ? null
        : String(o.source_label),
  };
}

export function parseTwinSearchResponse(body: unknown): TwinSearchResponse {
  if (!body || typeof body !== "object") {
    throw new Error("twin-search response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.query !== "string") {
    throw new Error("twin-search rejected: query must be string");
  }
  if (typeof o.count !== "number" || !Number.isInteger(o.count) || o.count < 0) {
    throw new Error("twin-search rejected: count must be nonnegative int");
  }
  if (!Array.isArray(o.hits)) {
    throw new Error("twin-search rejected: hits must be array");
  }
  const hits = o.hits.map((h, i) => parseTwinSearchHit(h, `hits[${i}]`));
  if (hits.length !== o.count) {
    // honesty: count must match hits length (server contract)
    throw new Error(
      `twin-search rejected: count ${o.count} != hits.length ${hits.length}`,
    );
  }
  return { query: o.query, count: o.count, hits };
}

export async function searchTwins(
  req: TwinSearchRequest,
): Promise<TwinSearchResponse> {
  const q = (req.q || "").trim();
  if (!q) {
    throw new Error("q must be non-empty");
  }
  const limit = req.limit ?? 20;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error("limit must be an integer in 1..100");
  }
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (req.parent_asset_id) {
    params.set("parent_asset_id", req.parent_asset_id);
  }
  const res = await apiFetch(`${API_BASE}/twins/search?${params.toString()}`, {
    method: "GET",
  });
  const raw = await readOkBody(res);
  return parseTwinSearchResponse(raw);
}
