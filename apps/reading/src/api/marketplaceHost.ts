/**
 * Marketplace host-into-account client.
 * Mirrors interfaces/research/api/marketplace_host_routes.py
 * Hosted view_format is always html (PDF ingest source only).
 */

import { API_BASE, apiFetch } from "../lib/api";

export type CatalogEntryRow = {
  book_id: string;
  title: string;
  author: string;
  license_class: string;
  is_free: boolean;
  source: string;
};

export type HostResultResponse = {
  document_id: string;
  owner_id: string;
  book_id: string;
  content_hash: string;
  title: string;
  license_class: string;
  already_hosted: boolean;
  source_format: string;
  library_document_ids: string[];
  view_format: "html";
  html: string;
  body_preview?: string;
  receipt_id?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`marketplace API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function fetchMarketplaceCatalog(): Promise<{
  entries: CatalogEntryRow[];
  count: number;
  view_format: "html";
}> {
  const res = await apiFetch(`${API_BASE}/marketplace/catalog`);
  return readJson(res);
}

export async function hostBookIntoAccount(body: {
  owner_id: string;
  book_id: string;
  receipt_id?: string | null;
  content_b64?: string | null;
}): Promise<HostResultResponse> {
  const res = await apiFetch(`${API_BASE}/marketplace/host`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<HostResultResponse>(res);
}

export async function purchaseAndHost(body: {
  owner_id: string;
  book_id: string;
  opaque_reference: string;
  content_b64: string;
  note?: string;
}): Promise<HostResultResponse> {
  const res = await apiFetch(`${API_BASE}/marketplace/purchase-and-host`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<HostResultResponse>(res);
}

export async function fetchAccountLibrary(ownerId: string): Promise<{
  owner_id: string;
  documents: Array<{
    document_id: string;
    title?: string;
    license_class?: string;
    view_format?: string;
  }>;
  count: number;
  view_format: "html";
  html: string;
}> {
  const res = await apiFetch(
    `${API_BASE}/marketplace/library/${encodeURIComponent(ownerId)}`,
  );
  return readJson(res);
}
