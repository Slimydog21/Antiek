import { API_BASE, apiFetch } from "../lib/api";

export type HostedDocumentReceipt = {
  document_id: string;
  owner_id: string;
  state: "ready" | "non_viewable";
  source_byte_hash: string;
  canonical_content_hash: string;
  source_format: string;
  title: string;
  document_loaded_event_id: string | null;
  already_hosted: boolean;
  non_viewable_reason: string | null;
  view_format: "html";
  html: string | null;
  intent?: "user_owned";
  source_event_id: string | null;
  author: string | null;
  page_count: number | null;
  word_count: number;
  projection_state: "pending" | "ready" | "non_viewable";
  projection_hash: string | null;
  projection_version: string | null;
  extraction_receipt: {
    extractor_version: string;
    source_byte_hash: string;
    extracted_content_hash: string;
    canonical_content_hash: string;
    source_format: string;
    word_count: number;
    minimum_viewable_words: number;
    truncated: boolean;
    viewable: boolean;
    non_viewable_reason: string | null;
  };
  chunk_anchors?: Array<{ chunk_id: string; anchor_id: string }>;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`hosted document API ${response.status}: ${body.slice(0, 240)}`);
  }
  return (await response.json()) as T;
}

export async function ingestHostedDocument(body: {
  content_b64: string;
  source_format: string;
  investigation_id: string;
  title?: string | null;
  source_uri?: string | null;
  intent?: "user_owned";
}): Promise<HostedDocumentReceipt> {
  return readJson<HostedDocumentReceipt>(
    await apiFetch(`${API_BASE}/hosted-documents/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchHostedDocument(
  documentId: string,
  citationChunkIds: string[] = [],
): Promise<HostedDocumentReceipt> {
  const params = new URLSearchParams();
  for (const chunkId of citationChunkIds) params.append("citation_chunk_id", chunkId);
  const suffix = params.size ? `?${params.toString()}` : "";
  return readJson<HostedDocumentReceipt>(
    await apiFetch(
      `${API_BASE}/hosted-documents/${encodeURIComponent(documentId)}/html${suffix}`,
      { cache: "no-store" },
    ),
  );
}

export type CitationPositionResult =
  | { status: "not_found" }
  | { status: "found"; index: number };

function parseCitationPositionResult(value: unknown, anchorCount: number): CitationPositionResult {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("hosted document API returned an invalid citation position");
  }
  const row = value as Record<string, unknown>;
  if (row.status === "not_found" && Object.keys(row).length === 1) return { status: "not_found" };
  if (
    row.status === "found"
    && Object.keys(row).sort().join("|") === "index|status"
    && Number.isInteger(row.index)
    && Number(row.index) >= 0
    && Number(row.index) < anchorCount
  ) return { status: "found", index: Number(row.index) };
  throw new Error("hosted document API returned an invalid citation position");
}

export async function fetchCitationPosition(
  documentId: string, receiptSha256: string, anchorCount: number,
): Promise<CitationPositionResult> {
  const params = new URLSearchParams({ receipt_sha256: receiptSha256, anchor_count: String(anchorCount) });
  return parseCitationPositionResult(await readJson<unknown>(await apiFetch(
    `${API_BASE}/hosted-documents/${encodeURIComponent(documentId)}/citation-position?${params.toString()}`,
    { cache: "no-store" },
  )), anchorCount);
}

export async function storeCitationPosition(
  documentId: string,
  body: { citation_evidence: unknown; index: number; anchor_count: number; mutation_key: string },
): Promise<{ status: "synced"; event_id: string; index: number }> {
  const value = await readJson<unknown>(await apiFetch(
    `${API_BASE}/hosted-documents/${encodeURIComponent(documentId)}/citation-position`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" },
  ));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("hosted document API returned an invalid citation position receipt");
  }
  const row = value as Record<string, unknown>;
  if (
    Object.keys(row).sort().join("|") !== "event_id|index|status"
    || row.status !== "synced"
    || typeof row.event_id !== "string"
    || !row.event_id
    || row.index !== body.index
  ) throw new Error("hosted document API returned an invalid citation position receipt");
  return { status: "synced", event_id: row.event_id, index: body.index };
}
