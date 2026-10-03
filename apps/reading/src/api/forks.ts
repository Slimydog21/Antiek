/**
 * forks.ts — the document-fork client (thread-merge + document fork SPR-01).
 *
 * POST /books/{id}/forks (idempotent on the caller's operation id), GET
 * /books/{id}/forks (forks-of-this AND forked-from in one read, so a reader
 * opening either side of a fork learns the whole depth-1 neighbourhood).
 * Responses are validated at the boundary: a malformed body throws an
 * ApiError, never a crash reading a non-row downstream. No fork-specific
 * body fetch exists — bodies stay behind the serve guard's routes alone.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface DocumentFork {
  fork_id: string;
  parent_document_id: string;
  fork_document_id: string;
  operation_id: string;
  fork_point_locator: string | null;
  note: string | null;
  generation_id: string | null;
  parent_body_sha256: string;
  fork_body_sha256: string;
  created_at: string;
  parent_title: string | null;
}

export interface ForksOfResponse {
  forks: DocumentFork[];
  forked_from: DocumentFork | null;
}

export interface CreateForkBody {
  /** The idempotency key: a replay returns the original fork (HTTP 200). */
  operation_id: string;
  note?: string;
  /** "page:<n>" or a unit-1 anchor ref; absent is the honest unknown. */
  fork_point_locator?: string;
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function parseFork(raw: unknown): DocumentFork {
  const r = raw as Partial<DocumentFork> | null;
  if (
    r === null ||
    typeof r !== "object" ||
    typeof r.fork_id !== "string" ||
    r.fork_id.length === 0 ||
    typeof r.parent_document_id !== "string" ||
    typeof r.fork_document_id !== "string" ||
    typeof r.operation_id !== "string" ||
    !(r.fork_point_locator === null || typeof r.fork_point_locator === "string") ||
    !(r.note === null || typeof r.note === "string") ||
    !(r.generation_id === null || typeof r.generation_id === "string") ||
    !isSha256(r.parent_body_sha256) ||
    !isSha256(r.fork_body_sha256) ||
    typeof r.created_at !== "string" ||
    !(r.parent_title === null || typeof r.parent_title === "string")
  ) {
    throw new ApiError("forks: malformed fork row", 0, JSON.stringify(raw));
  }
  return {
    fork_id: r.fork_id,
    parent_document_id: r.parent_document_id,
    fork_document_id: r.fork_document_id,
    operation_id: r.operation_id,
    fork_point_locator: r.fork_point_locator ?? null,
    note: r.note ?? null,
    generation_id: r.generation_id ?? null,
    parent_body_sha256: r.parent_body_sha256,
    fork_body_sha256: r.fork_body_sha256,
    created_at: r.created_at,
    parent_title: r.parent_title ?? null,
  };
}

function parseForksOf(raw: unknown): ForksOfResponse {
  const r = raw as Partial<ForksOfResponse> | null;
  if (r === null || typeof r !== "object" || !Array.isArray(r.forks)) {
    throw new ApiError("forks: malformed forks-of response", 0, JSON.stringify(raw));
  }
  return {
    forks: r.forks.map(parseFork),
    forked_from: r.forked_from == null ? null : parseFork(r.forked_from),
  };
}

async function throwUnlessOk(resp: Response, label: string): Promise<void> {
  if (!resp.ok) {
    throw new ApiError(`${label} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
}

/** Create the fork. A 422 carries the rights refusal (a gated book grants
 *  no transformation right); a 409 the depth-1 limit. Both are ApiError
 *  with the server's detail as the body — the caller names the state,
 *  never fakes a success. */
export async function createFork(
  documentId: string,
  body: CreateForkBody,
): Promise<DocumentFork> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/forks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: null, fork_point_locator: null, ...body }),
  });
  await throwUnlessOk(resp, "POST /books/{id}/forks");
  return parseFork(await resp.json());
}

/** Forks of this document AND the row where this document is the fork. */
export async function listForks(documentId: string): Promise<ForksOfResponse> {
  const resp = await apiFetch(`${API_BASE}/books/${encodeURIComponent(documentId)}/forks`);
  if (resp.status === 404) throw new ApiError("book_not_found", 404, await resp.text());
  await throwUnlessOk(resp, "GET /books/{id}/forks");
  return parseForksOf(await resp.json());
}
