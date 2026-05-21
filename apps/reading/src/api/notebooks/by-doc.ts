/**
 * Per-document notebook API — type stubs.
 *
 * STATUS: provisional stub committed in S6 to unblock typecheck.
 *
 * The real implementation belongs to the SPR-09 notebook track
 * (`AntiekPersistence default + SaveAs surface`, commit ea62ada). That
 * track introduced `src/modes/Notebook/SaveAs.tsx` which imports from
 * `../../api/notebooks/by-doc`, but the backing module never landed.
 * Without this stub `tsc -b` fails and the UI redesign sprints get
 * blocked on a foreign-track gap.
 *
 * When the SPR-09 follow-up lands the real API client (HTTP calls to
 * `/api/notebooks/by-doc/<doc>/save`, `/export?format=pdf`, etc.),
 * replace this file. Until then `savePerDocNotebook` returns the
 * payload it was given (so the call shape is preserved) and the
 * shapes mirror SaveAs.tsx's usage.
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
  content_json: unknown;
  blocks: unknown[];
  updated_at?: string;
  version?: number;
  archive_url?: string | null;
};

/**
 * Stub implementation. Posts no HTTP call yet; returns the payload
 * echoed back as a PerDocNotebookResponse so the SaveAs surface can
 * unit-test against the typed shape without a backend.
 *
 * Real implementation contract (when it lands):
 *
 *   POST /api/notebooks/by-doc/{documentId}/save
 *   body: PerDocNotebookSavePayload
 *   200:  PerDocNotebookResponse
 */
export async function savePerDocNotebook(
  documentId: string,
  payload: PerDocNotebookSavePayload,
): Promise<PerDocNotebookResponse> {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn(
      "[antiek/api/notebooks/by-doc] savePerDocNotebook is a stub (S6). " +
        "The real call lands when the SPR-09 follow-up commits. " +
        `doc=${documentId} kind=${payload.save_kind}`,
    );
  }
  return {
    notebook_id: payload.notebook_id,
    content_json: payload.content_json,
    blocks: payload.blocks,
    updated_at: new Date().toISOString(),
    version: 0,
    archive_url: null,
  };
}
