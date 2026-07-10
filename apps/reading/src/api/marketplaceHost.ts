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
  /** Residual (lw): research-domain tags (science, philosophy, …). */
  subjects?: string[];
};

/** Residual (ma/mb): Antiek-bench usage event from host/purchase path. */
export type MarketplaceUsageEvent = {
  task_class?: string;
  outcome?: string;
  prompt_hint?: string;
  source?: string;
  recorded?: boolean;
  record_skipped?: string;
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
  /** Residual (ma): book_qa usage feed for recursive suite rewrite. */
  usage_event?: MarketplaceUsageEvent;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`marketplace API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

/** Residual (iq/lw/ly): catalog honesty fields from GET /marketplace/catalog. */
export type MarketplaceCatalogResponse = {
  entries: CatalogEntryRow[];
  count: number;
  view_format: "html";
  by_source?: Record<string, number>;
  by_license?: Record<string, number>;
  /** Residual (lw): multi-label research-domain counts. */
  by_subject?: Record<string, number>;
  public_domain_count?: number;
  purchased_count?: number;
  free_count?: number;
  payment_rails?: string;
  /** Residual (ly): HTML-first catalog projection for browse window. */
  html?: string;
};

export async function fetchMarketplaceCatalog(opts?: {
  freeOnly?: boolean;
  subject?: string;
  source?: string;
  includeHtml?: boolean;
}): Promise<MarketplaceCatalogResponse> {
  const params = new URLSearchParams();
  if (opts?.freeOnly) params.set("free_only", "true");
  if (opts?.subject) params.set("subject", opts.subject);
  if (opts?.source) params.set("source", opts.source);
  if (opts?.includeHtml === false) params.set("include_html", "false");
  const qs = params.toString();
  const res = await apiFetch(
    `${API_BASE}/marketplace/catalog${qs ? `?${qs}` : ""}`,
  );
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
    /** Residual (abu): free inventory for library free honesty (parity free doctrine). */
    is_free?: boolean;
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

/** Residual (do): rehydrate hosted document HTML body for library open. */
export type HostedDocumentHtmlResponse = {
  document_id: string;
  view_format: "html" | string;
  html: string;
  title?: string;
  license_class?: string;
};

export async function fetchHostedDocumentHtml(
  documentId: string,
): Promise<HostedDocumentHtmlResponse> {
  const res = await apiFetch(
    `${API_BASE}/marketplace/documents/${encodeURIComponent(documentId)}/html`,
  );
  return readJson(res);
}
