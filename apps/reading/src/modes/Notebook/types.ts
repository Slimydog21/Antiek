/**
 * Notebook surface types — mirror of the Python NotebookResponse
 * shape from interfaces/research/api/app.py.
 *
 * NOT in generated/types.ts because these are API-layer response
 * envelopes, not substrate events. Drift here = silent schema
 * break; CI gate (codegen staleness) doesn't catch it. Operator
 * must keep these in sync with the FastAPI Pydantic models manually
 * until Sprint 18+ extends the codegen to API response shapes.
 */

export interface NotebookBlockResponse {
  block_id: string;
  block_index: number;
  block_type:
    | "prose"
    | "region_embed"
    | "claim_card"
    | "note"
    | "question_card"
    | "cross_doc_link"
    | "chat_exchange"
    | "master_md_section"
    | "image"
    | "latex";
  ref_id: string | null;
  content_json: Record<string, unknown>;
  created_at: string;
}

export interface NotebookResponse {
  notebook_id: string;
  title: string;
  investigation_id: string | null;
  document_id: string | null;
  content_class: "user_owned" | "user_public_contribution";
  created_at: string;
  updated_at: string;
  blocks: NotebookBlockResponse[];
}

/** Props the Notebook surface accepts for story/test injection.
 *  Every field is optional so stories can render isolated states
 *  without a real router or API transport. */
export interface NotebookSurfaceProps {
  notebookIdOverride?: string | null;
  initialNotebook?: NotebookResponse | null;
  initialLoading?: boolean;
  initialError?: string | null;
  /** false → all mutation helpers are no-ops and controls are inert.
   *  Stories set this to false so no transport is possible. */
  executionEnabled?: boolean;
  initialMutationPending?: boolean;
}
