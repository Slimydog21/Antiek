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
): Promise<HostedDocumentReceipt> {
  return readJson<HostedDocumentReceipt>(
    await apiFetch(
      `${API_BASE}/hosted-documents/${encodeURIComponent(documentId)}/html`,
    ),
  );
}
