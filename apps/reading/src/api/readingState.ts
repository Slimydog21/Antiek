/**
 * readingState.ts — the reading-state bus client (reading-global SPR-01).
 *
 * GET/PUT /books/{id}/reading-state — ONE position per owner+document
 * across every reader mount and device. Refs and numbers only: a page
 * index, an optional unit-1 anchor ref, the (empty-in-v1) prefs map, and
 * the optimistic-concurrency revision. A GET 404 is a lawful "no position
 * recorded yet" — null, never a fabricated page 0. Responses are validated
 * at the boundary: a malformed body is an honest unreachable (the hook's
 * sessionStorage fallback carries on), never a crash reading a non-row.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface ReadingState {
  document_id: string;
  page_index: number;
  anchor_ref: string | null;
  prefs: Record<string, unknown>;
  revision: number;
  updated_at: string;
}

export interface ReadingStatePutBody {
  page_index: number;
  anchor_ref?: string | null;
  prefs?: Record<string, unknown>;
  /** The revision the client last saw (0 for a first write). */
  revision: number;
}

function parseState(raw: unknown, documentId: string): ReadingState {
  const r = raw as Partial<ReadingState> | null;
  if (
    r === null ||
    typeof r !== "object" ||
    typeof r.document_id !== "string" ||
    r.document_id !== documentId ||
    typeof r.page_index !== "number" ||
    !Number.isSafeInteger(r.page_index) ||
    r.page_index < 0 ||
    typeof r.revision !== "number" ||
    !Number.isSafeInteger(r.revision) ||
    r.revision < 0 ||
    !(r.anchor_ref === null || typeof r.anchor_ref === "string") ||
    (typeof r.anchor_ref === "string" && (r.anchor_ref.length === 0 || r.anchor_ref.length > 20)) ||
    typeof r.prefs !== "object" ||
    r.prefs === null ||
    Array.isArray(r.prefs) ||
    Object.keys(r.prefs).length !== 0 ||
    typeof r.updated_at !== "string" ||
    r.updated_at.length === 0
  ) {
    throw new ApiError("reading-state: malformed response body", 0, JSON.stringify(raw));
  }
  return {
    document_id: r.document_id,
    page_index: r.page_index,
    anchor_ref: r.anchor_ref == null ? null : String(r.anchor_ref),
    prefs: r.prefs,
    revision: r.revision,
    updated_at: r.updated_at,
  };
}

/** GET the owner's row — null when no position is recorded (404). */
export async function getReadingState(documentId: string): Promise<ReadingState | null> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/reading-state`,
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new ApiError(
      `GET /books/{id}/reading-state failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return parseState(await resp.json(), documentId);
}

/** PUT the position with the last-seen revision. A stale revision throws
 *  ApiError 409 (never a silent clobber — the caller re-reads; the server
 *  value wins only when no later local turn remains unsettled). */
export async function putReadingState(
  documentId: string,
  body: ReadingStatePutBody,
): Promise<ReadingState> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/reading-state`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anchor_ref: null, prefs: {}, ...body }),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `PUT /books/{id}/reading-state failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return parseState(await resp.json(), documentId);
}
