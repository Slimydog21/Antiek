import { API_BASE, ApiError, apiFetch } from "../../lib/api";

/**
 * Per-document notebook API.
 *
 * This is the SaveAs bridge for document-bound notebooks: the caller carries a
 * stable notebook id, the document id scopes the binding, and the backend saves
 * through the same notebook_blocks substrate used by the main editor.
 */

/** What SaveAs.tsx writes to the server on save. Inferred from usage. */
export type PerDocNotebookSavePayload = {
  notebook_id: string;
  content_json: unknown;
  blocks: unknown[];
  save_kind: "explicit" | "autosave";
};

/** Server response shape. SaveAs.tsx echoes this back via onSaved. */
export type PerDocNotebookResponse = {
  notebook_id: string;
  document_id?: string | null;
  content_json: unknown;
  blocks: unknown[];
  updated_at?: string;
  version?: number;
  archive_url?: string | null;
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function optionalString(value: unknown): string | undefined {
  return value == null ? undefined : nonEmptyString(value) ?? undefined;
}

function nullableString(value: unknown): string | null | undefined {
  return value == null ? null : nonEmptyString(value) ?? undefined;
}

function optionalSafeInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : undefined;
}

export function safePerDocNotebookResponse(
  value: unknown,
  fallbackDocumentId: string,
): PerDocNotebookResponse {
  const body = record(value);
  const notebookId = nonEmptyString(body?.notebook_id);
  if (!body || !notebookId) {
    throw new ApiError("Malformed per-document notebook save response", 502, "");
  }
  return {
    notebook_id: notebookId,
    document_id: nullableString(body.document_id) ?? fallbackDocumentId,
    content_json: body.content_json ?? null,
    blocks: Array.isArray(body.blocks) ? body.blocks : [],
    updated_at: optionalString(body.updated_at),
    version: optionalSafeInteger(body.version),
    archive_url: nullableString(body.archive_url),
  };
}

export async function savePerDocNotebook(
  documentId: string,
  payload: PerDocNotebookSavePayload,
): Promise<PerDocNotebookResponse> {
  const resp = await apiFetch(
    `${API_BASE}/notebooks/by-doc/${encodeURIComponent(documentId)}/save`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!resp.ok) {
    throw new ApiError(
      `POST /notebooks/by-doc/${documentId}/save failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return safePerDocNotebookResponse(await resp.json(), documentId);
}
