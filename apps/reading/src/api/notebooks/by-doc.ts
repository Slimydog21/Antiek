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
  return resp.json();
}
