/**
 * reformat.ts — the reformat flow's client (reformat-provenance SPR-02).
 *
 * POST /books/{id}/reformats (the generation call — the pipeline is the
 * only provenance writer) · GET /documents/{id}/provenance (the review
 * surface's structured read — 404 on a plain document, honestly null) ·
 * the unit-5 contract paths (fork/merge) with HONEST DEGRADATION: on a
 * stack without them they 404, and the caller names the pending state —
 * never a fake success.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export type ReformatMode = "time_window" | "themes";

export interface ReformatResponse {
  generation_id: string;
  derived_document_id: string;
  /** The generation thread — the engagement that stays in the pane. */
  thread_id: string;
  bite_count: number;
  contribution_classes: string[];
  mostly_generated: boolean;
  reclassed_verbatim: number;
  null_source_share: number;
}

export interface ProvenanceBite {
  bite_id: string;
  ordinal: number;
  contribution_class: string;
  /** The unit-1 anchor payloads into the CORE document (null = the honest
   *  no-direct-source connective tissue). */
  source_refs: { node_id: string; start_scalar: number; end_scalar: number }[] | null;
  /** The core passage's page per source ref (server-resolved). */
  source_page_hints: (number | null)[];
  investigation_id: string | null;
  byte_verified: boolean;
}

export interface ProvenanceResponse {
  document_id: string;
  generation: {
    generation_id: string;
    source_document_id: string;
    /** The source's TITLE (human terms — a raw id is never a label). */
    source_title: string | null;
    prompt: string;
    model: string;
    params: Record<string, unknown>;
    mostly_generated: boolean;
    created_at: string;
  };
  bites: ProvenanceBite[];
}

export async function postReformat(
  documentId: string,
  body: { prompt: string; mode: ReformatMode; model?: string },
): Promise<ReformatResponse> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/reformats`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /books/{id}/reformats failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return (await resp.json()) as ReformatResponse;
}

/** The derived document's provenance — null when the document is not
 *  derived (404), honestly. Boundary validation: a malformed payload is
 *  ALSO null (the review surface is additive — a garbage body must never
 *  crash the rail). */
export async function getProvenance(
  documentId: string,
): Promise<ProvenanceResponse | null> {
  const resp = await apiFetch(
    `${API_BASE}/documents/${encodeURIComponent(documentId)}/provenance`,
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new ApiError(
      `GET /documents/{id}/provenance failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const raw = (await resp.json()) as Partial<ProvenanceResponse>;
  if (
    !raw.generation ||
    typeof raw.generation !== "object" ||
    typeof raw.generation.generation_id !== "string" ||
    !Array.isArray(raw.bites)
  ) {
    return null; // not a provenance payload — render nothing, honestly
  }
  return raw as ProvenanceResponse;
}

/** "Officially fork" — the unit-5 contract path (POST /books/{id}/forks),
 *  carrying the generation record's refs. On a stack without the fork API
 *  this 404s — the caller names the pending state, never fakes it. */
export async function postFork(
  sourceDocumentId: string,
  body: { derived_document_id: string; generation_id: string; note?: string },
): Promise<unknown> {
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(sourceDocumentId)}/forks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /books/{id}/forks failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}

/** The pull-a-snippet probe (SPR-03): the core document's passage,
 *  gate-served — a withheld source's probe returns metadata only (text
 *  null), never body. */
export interface PassageSnippet {
  servable: boolean;
  text: string | null;
  page_index_hint: number | null;
  chunk_id: string;
  start_scalar: number;
  end_scalar: number;
}

export async function getPassageSnippet(
  documentId: string,
  span: { node_id: string; start_scalar: number; end_scalar: number },
): Promise<PassageSnippet> {
  const params = new URLSearchParams({
    chunk_id: span.node_id,
    start_scalar: String(span.start_scalar),
    end_scalar: String(span.end_scalar),
  });
  const resp = await apiFetch(
    `${API_BASE}/books/${encodeURIComponent(documentId)}/passage?${params}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /books/{id}/passage failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return (await resp.json()) as PassageSnippet;
}
/** "Merge later" — the unit-5 merge shape (fork-merge route family).
 *  Same honest-degradation rule: 404 on a stack without it. */
export async function postForkMerge(
  forkId: string,
  body: { from_derived_document_id: string; generation_id: string },
): Promise<unknown> {
  const resp = await apiFetch(
    `${API_BASE}/forks/${encodeURIComponent(forkId)}/merge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /forks/{id}/merge failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json();
}
