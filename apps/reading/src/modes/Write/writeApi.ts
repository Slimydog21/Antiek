/**
 * Typed client for the Write REST surface (`/write/*`,
 * interfaces/research/api/write_routes.py).
 *
 * Kept in its own module (not the shared, multi-stream-edited lib/api.ts)
 * for the same collision-avoidance reason the router itself is a separate
 * file. Thin wrappers over the app's ``apiFetch`` (which carries the
 * Cloudflare Access cookies).
 */

import { API_BASE, ApiError, apiFetch } from "../../lib/api";

export interface RepositoryHit {
  node_id: string;
  label: string;
  node_type: string;
  source_tier: number | null;
  document_id: string | null;
  document_title: string | null;
  score: number;
}

export interface FolderSummary {
  folder_id: string;
  name: string;
  member_count: number;
}

export interface PlaceBlockBody {
  section_id: string;
  block_kind: "insight" | "open_question" | "claim";
  provenance_kind: "graph_node";
  node_id: string;
  block_index: number;
  deliverable_id?: string;
}

async function _json<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) {
    throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json() as Promise<T>;
}

export async function searchRepository(opts: {
  q?: string;
  folderId?: string;
  sourceDocumentId?: string;
  limit?: number;
}): Promise<RepositoryHit[]> {
  const url = new URL(`${API_BASE}/write/blocks/search`, window.location.origin);
  if (opts.q) url.searchParams.set("q", opts.q);
  if (opts.folderId) url.searchParams.set("folder_id", opts.folderId);
  if (opts.sourceDocumentId) url.searchParams.set("source_document_id", opts.sourceDocumentId);
  if (opts.limit) url.searchParams.set("limit", String(opts.limit));
  const body = await _json<{ hits: RepositoryHit[] }>(
    await apiFetch(url.toString()), "GET /write/blocks/search",
  );
  return body.hits;
}

export async function listFolders(): Promise<FolderSummary[]> {
  const body = await _json<{ folders: FolderSummary[] }>(
    await apiFetch(`${API_BASE}/write/folders`), "GET /write/folders",
  );
  return body.folders;
}

export async function createFolder(name: string): Promise<string> {
  const body = await _json<{ folder_id: string }>(
    await apiFetch(`${API_BASE}/write/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
    "POST /write/folders",
  );
  return body.folder_id;
}

export async function addFolderBlock(folderId: string, nodeId: string): Promise<void> {
  await _json<unknown>(
    await apiFetch(`${API_BASE}/write/folders/${encodeURIComponent(folderId)}/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId }),
    }),
    "POST /write/folders/{id}/blocks",
  );
}

/** Place a block in the outline (the drop target's commit). Returns the
 * new outline_block_id. */
export async function placeBlock(body: PlaceBlockBody): Promise<string> {
  const r = await _json<{ outline_block_id: string }>(
    await apiFetch(`${API_BASE}/write/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/blocks",
  );
  return r.outline_block_id;
}
