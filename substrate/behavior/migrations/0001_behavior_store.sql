-- ============================================================
-- 0001_behavior_store.sql
-- Wrestle Evolution SPR-01 · M2 · Tier-1 behavior store
--
-- Schema-distinct from substrate/event_log/ (which is IP/audit
-- trajectory data) and from substrate/graph/ (knowledge graph).
-- This table is the substrate for on-policy RL training data and
-- is subject to a different privacy regime (opt-in consent +
-- DP shuffler on export). See substrate/behavior/PRIVACY.md.
--
-- Idempotent: every CREATE uses IF NOT EXISTS. Safe to re-run on
-- a fresh DB and on a production-shape DB; the migrate command
-- in schema.py exercises both paths.
-- ============================================================

-- ----------------------------------------------------------------
-- behavior_events — RL-shaped event rows
--
-- Column groups (logical, not declarative):
--   identity   : event_id, user_id, session_id, document_id
--   when       : timestamp_utc
--   action     : event_type, state, action
--   outcome    : outcome (nullable; backfilled later)
--   reward     : reward_proxy_immediate / _medium / _deep (nullable
--                at write; downstream backfill workers populate)
--   policy     : consent_version (snapshot of the consent regime at
--                write time so future opt-out reasoning is precise)
--   dp         : dp_shuffler_batch_id (null until export runs; the
--                shuffler stamps a batch id when a row leaves the
--                raw store)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS behavior_events (
    -- Identity ----------------------------------------------------
    event_id        TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    -- document_id is nullable: events like document_opened name a
    -- document, but a future session-start ping would not. The FK
    -- target is documents.document_id — see graph schema. We only
    -- assert the FK if the documents table exists (it does post-
    -- SPR-03 ingest); the constraint is created via ALTER TABLE in
    -- a follow-up block so this migration runs cleanly even before
    -- graph schema initialization.
    document_id     TEXT,

    -- When --------------------------------------------------------
    timestamp_utc   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Action ------------------------------------------------------
    -- event_type values are enforced by the application layer (the
    -- closed BehaviorEventType enum + schemas/<type>.json files).
    -- We do NOT add a CHECK constraint over a string list here
    -- because DuckDB would force a schema migration every time the
    -- taxonomy grows; the closed-enum invariant lives at the emit
    -- API boundary.
    event_type      TEXT NOT NULL,
    state           TEXT NOT NULL,   -- JSON string (Researchmaxx
                                     -- VARIANT-deferral convention;
                                     -- see graph/schema.py)
    action          TEXT NOT NULL,   -- JSON string

    -- Outcome -----------------------------------------------------
    outcome         TEXT,            -- JSON string; nullable

    -- Reward proxies ---------------------------------------------
    -- All three are nullable at write. The immediate worker can
    -- populate _immediate within seconds; medium/deep run on a
    -- cron with notebook/deliverable joins. Float to allow shaped
    -- signals (not just 0/1).
    reward_proxy_immediate  DOUBLE,
    reward_proxy_medium     DOUBLE,
    reward_proxy_deep       DOUBLE,

    -- Policy snapshot --------------------------------------------
    consent_version INTEGER NOT NULL,

    -- DP shuffler stamp ------------------------------------------
    -- NULL until the row has passed through the shuffler on
    -- export. The shuffler stamps the batch id on the source row
    -- after it writes the shuffled output, so we can audit which
    -- rows contributed to which training corpus.
    dp_shuffler_batch_id TEXT
);

-- Indexes per spec M2 ----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_behavior_events_user_time
    ON behavior_events (user_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_behavior_events_type_time
    ON behavior_events (event_type, timestamp_utc);

-- Auxiliary index for the immediate-reward worker, which scans by
-- session_id to compute per-session signals (e.g., "was the link
-- surfaced clicked within 5s in the same session?"). Not required
-- by the spec but cheap and load-bearing for M5.
CREATE INDEX IF NOT EXISTS idx_behavior_events_session
    ON behavior_events (session_id, timestamp_utc);

-- Index for the DP-shuffler export selector: pulls rows where the
-- batch id is still NULL. DuckDB does not yet support partial
-- indexes (NotImplementedException), so the index is over the
-- whole column; queries use IS NULL on it. The selectivity is
-- still high in practice because unshuffled rows dominate until
-- the first export runs.
CREATE INDEX IF NOT EXISTS idx_behavior_events_dp_batch
    ON behavior_events (dp_shuffler_batch_id);

-- ----------------------------------------------------------------
-- dp_shuffler_batches — provenance of each export
--
-- One row per export invocation. Carries the configured epsilon /
-- delta plus the size of the batch. Operator can audit
-- `SELECT * FROM dp_shuffler_batches ORDER BY shuffled_at DESC`.
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dp_shuffler_batches (
    batch_id        TEXT PRIMARY KEY,
    shuffled_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_count       INTEGER NOT NULL,
    epsilon         DOUBLE NOT NULL,
    delta           DOUBLE NOT NULL,
    surface_name    TEXT NOT NULL,
    -- The shuffler perturbs ordering and timestamps; we record the
    -- floor/ceiling so downstream backtest can reason about how
    -- much jitter was applied.
    timestamp_jitter_max_s DOUBLE NOT NULL,
    notes           TEXT
);
