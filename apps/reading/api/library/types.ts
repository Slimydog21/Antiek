// SPR-03 / M1 — Universal-library ingestion API types.
//
// Contract types for the POST /api/library/ingest + GET
// /api/library/ingest/{job_id} endpoints. SPR-06 (Reading UI) imports
// these to render the paste-URL flow without re-deriving the shapes.
//
// The Python side of the contract lives in
// services/ingestion/pipeline.py (IngestResult dataclass) +
// interfaces/research/api/library.py (FastAPI Pydantic models). These
// TS types are hand-maintained to mirror those shapes — the polyglot
// seam pattern from docs/architecture_notes.md §11.1.

/** Content-type label returned by the detection pass. */
export type IngestContentType =
  | "pdf"
  | "html_article"
  | "epub"
  | "arxiv"
  | "unknown";

/** Job state machine — same set as the ingestion_jobs DDL CHECK. */
export type IngestJobStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed";

/** POST /api/library/ingest body. ``source_metadata`` is opaque
 *  per-caller context (e.g. a reading-app session id, a "saved from
 *  recommendation" flag) that round-trips into the job row's
 *  metadata column. */
export interface IngestRequest {
  url: string;
  user_id: string;
  source_metadata?: Record<string, unknown>;
}

/** POST /api/library/ingest response.
 *
 * One of:
 *  - cache-hit / synchronous-fast path: both ``job_id`` and
 *    ``document_id`` set, status "succeeded";
 *  - async path: ``job_id`` set, ``document_id`` null,
 *    status "pending" (poll GET /api/library/ingest/{job_id});
 *  - fast-fail (malformed URL, immediate validation failure):
 *    status "failed" with ``error`` populated. */
export interface IngestResponse {
  job_id: string;
  document_id: string | null;
  status: IngestJobStatus;
  content_type: IngestContentType | null;
  error: string | null;
  paywalled?: boolean;
}

/** GET /api/library/ingest/{job_id} response — the full job row. */
export interface IngestJob {
  job_id: string;
  url: string;
  user_id: string;
  investigation_id: string;
  status: IngestJobStatus;
  content_type: IngestContentType | null;
  document_id: string | null;
  error: string | null;
  error_detail: string | null;
  attempts: number;
  created_at: string;  // ISO 8601
  updated_at: string;  // ISO 8601
  metadata: Record<string, unknown>;
}
