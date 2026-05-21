// SPR-08 / M1 — Per-document notebook API client.
//
// The actual endpoints are FastAPI Python (interfaces/research/api/);
// this is the TypeScript client the reading surface imports. Polyglot-seam
// pattern: the call shape lives in one place so the surface doesn't
// string-format URLs.
//
// Endpoints (paired with services/notebooks/ in Python):
//
//   GET    /api/notebooks/by-doc/{document_id}
//      → fetch (or auto-create on first hit) the per-document notebook
//        for the authenticated user; response includes ordered + demoted
//        block lists.
//
//   POST   /api/notebooks/by-doc/{document_id}/save
//      → debounced auto-save / Cmd+S explicit save; body carries the
//        TipTap document JSON + the structured block list.
//
//   POST   /api/notebooks/by-doc/{document_id}/blocks/{block_id}/demote
//      → toggle demote state. Demoting fires
//        notebook_block_demoted in the behavior store via the surface,
//        not here — see PerDocNotebook.tsx.
//
//   POST   /api/notebooks/by-doc/{document_id}/blocks/{block_id}/edit
//      → patch one block's content_json; bumps edited_at.
//
// Until the FastAPI route handlers land in a follow-up PR (Sprint 18
// dispatch lock), this module's call sites resolve via fetch() but
// the surface degrades gracefully on 404 (renders an empty notebook
// + a "API not available" banner). The contract below IS the spec
// the FastAPI handlers must implement; drift here = silent break.

// Closed taxonomy mirror of services/notebooks/blocks.py::BlockType.
// Hand-kept in sync with the Python until codegen extends to
// service-layer types (Sprint 21+).
export const BlockType = {
  HIGHLIGHT_CARD: "highlight_card",
  VOICE_BLOCK: "voice_block",
  AI_QA: "ai_qa",
  CITE_LINK: "cite_link",
  CROSS_DOC_JUMP: "cross_doc_jump",
  PROSE: "prose",
} as const;

export type BlockTypeValue = (typeof BlockType)[keyof typeof BlockType];

export const ALL_BLOCK_TYPES: readonly BlockTypeValue[] =
  Object.values(BlockType);

/** One block as the API returns it. ``content_json`` shape is block-
 * type-specific; the per-type renderers in
 * apps/reading/src/modes/Notebook/blocks/ know how to read it. */
export interface PerDocNotebookBlock {
  block_id: string;
  notebook_id: string;
  block_type: BlockTypeValue;
  source_event_ids: string[];
  content_json: Record<string, unknown>;
  position: number;
  demoted_at: string | null;
  edited_at: string | null;
  created_at: string;
  document_id: string | null;
}

/** Per-doc notebook envelope. */
export interface PerDocNotebookResponse {
  notebook_id: string;
  user_id: string;
  document_id: string;
  title: string | null;
  content_json: Record<string, unknown>;
  format_version: number;
  created_at: string;
  last_saved_at: string;
  blocks: PerDocNotebookBlock[];
}

/** API base resolution mirrors apps/reading/api/library/ingest.ts —
 * VITE_ANTIEK_API_BASE in prod, empty string for dev-proxy. */
function apiBase(): string {
  const env = (import.meta as { env?: { VITE_ANTIEK_API_BASE?: string } }).env;
  return (env?.VITE_ANTIEK_API_BASE || "").replace(/\/+$/, "");
}

/** Per-doc notebook client error. The status code distinguishes the
 * "API not implemented yet" case (404) from a real failure (5xx). */
export class PerDocNotebookError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "PerDocNotebookError";
    this.status = status;
    this.detail = detail;
  }
}

/** GET /api/notebooks/by-doc/{document_id}. Auto-creates on first call.
 *
 *  On 404 (the route handler isn't implemented yet) callers SHOULD
 *  catch ``PerDocNotebookError`` and render the empty-state banner.
 *  This lets the surface ship before the FastAPI route lands.
 */
export async function getPerDocNotebook(
  documentId: string,
  init?: RequestInit,
): Promise<PerDocNotebookResponse> {
  const url = `${apiBase()}/api/notebooks/by-doc/${encodeURIComponent(
    documentId,
  )}`;
  const res = await fetch(url, {
    ...init,
    method: "GET",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new PerDocNotebookError(
      `GET /api/notebooks/by-doc/${documentId} failed: HTTP ${res.status}`,
      res.status,
      detail,
    );
  }
  return res.json();
}

/** POST /api/notebooks/by-doc/{document_id}/save — explicit or debounced save. */
export async function savePerDocNotebook(
  documentId: string,
  body: {
    notebook_id: string;
    content_json: Record<string, unknown>;
    blocks: PerDocNotebookBlock[];
    save_kind?: "auto" | "explicit";
  },
  init?: RequestInit,
): Promise<PerDocNotebookResponse> {
  const url = `${apiBase()}/api/notebooks/by-doc/${encodeURIComponent(
    documentId,
  )}/save`;
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new PerDocNotebookError(
      `POST save failed: HTTP ${res.status}`,
      res.status,
      detail,
    );
  }
  return res.json();
}

/** POST /api/notebooks/by-doc/{document_id}/blocks/{block_id}/demote */
export async function toggleDemoteBlock(
  documentId: string,
  blockId: string,
  demoted: boolean,
  init?: RequestInit,
): Promise<PerDocNotebookBlock> {
  const url =
    `${apiBase()}/api/notebooks/by-doc/${encodeURIComponent(documentId)}` +
    `/blocks/${encodeURIComponent(blockId)}/demote`;
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
    body: JSON.stringify({ demoted }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new PerDocNotebookError(
      `POST demote failed: HTTP ${res.status}`,
      res.status,
      detail,
    );
  }
  return res.json();
}

/** POST /api/notebooks/by-doc/{document_id}/blocks/{block_id}/edit */
export async function editPerDocBlock(
  documentId: string,
  blockId: string,
  contentJson: Record<string, unknown>,
  init?: RequestInit,
): Promise<PerDocNotebookBlock> {
  const url =
    `${apiBase()}/api/notebooks/by-doc/${encodeURIComponent(documentId)}` +
    `/blocks/${encodeURIComponent(blockId)}/edit`;
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
    body: JSON.stringify({ content_json: contentJson }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new PerDocNotebookError(
      `POST edit failed: HTTP ${res.status}`,
      res.status,
      detail,
    );
  }
  return res.json();
}
