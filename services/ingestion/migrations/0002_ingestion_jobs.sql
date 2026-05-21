-- Sprint SPR-03 / M7 — async ingestion job log.
--
-- The POST /api/library/ingest endpoint returns a job_id for any URL
-- that requires real fetching (everything except cache hits). The
-- client polls /api/library/ingest/{job_id} until status is
-- 'succeeded' or 'failed'. ingestion_jobs is where job state lives.
--
-- State machine:
--   pending    → queued, fetch not yet started
--   running    → fetcher / extractor / pipeline in progress
--   succeeded  → terminal: document_id is non-null, error is null
--   failed     → terminal: error is non-null, document_id may be null
--                (failure before extraction) or set (failure after
--                document row was committed but a downstream step
--                failed — pipeline writes are transactional so this
--                shouldn't happen in normal operation; the column is
--                still there for diagnostic value).
--
-- Transactional ingest: M7 acceptance says "partial results are not
-- committed." The pipeline opens a single connect_write context per
-- ingest and writes the documents+chunks+nodes rows inside it. If
-- anything raises before the context exits, no rows commit. The job
-- still updates to 'failed' (a separate connect_write) so the API
-- has something to return — the job-log write is not in the same
-- transaction as the substrate write (different concerns, different
-- failure surfaces).

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id          TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    investigation_id TEXT NOT NULL DEFAULT '__operator__',
    status          TEXT NOT NULL CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed'
    )),
    content_type    TEXT,                -- pdf | html_article | epub | arxiv | unknown
    document_id     TEXT,                -- set on success
    error           TEXT,                -- set on failure; short reason string
    error_detail    TEXT,                -- optional longer trace
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata        TEXT                 -- JSON
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status
    ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_user
    ON ingestion_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_created
    ON ingestion_jobs(created_at);
