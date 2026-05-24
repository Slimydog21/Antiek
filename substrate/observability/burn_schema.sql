-- substrate/observability/burn — append-only per-LLM-call cost ledger.
CREATE TABLE IF NOT EXISTS burn_events (
    event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                    TEXT    NOT NULL,
    session_id            TEXT    NOT NULL,
    project_id            TEXT,
    call_id               TEXT    NOT NULL,
    model                 TEXT    NOT NULL,
    tool_id               TEXT,
    input_tokens          INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    cached_tokens         INTEGER NOT NULL DEFAULT 0,
    error                 TEXT,
    extension_ids_active  TEXT
);

CREATE INDEX IF NOT EXISTS idx_burn_ts         ON burn_events(ts);
CREATE INDEX IF NOT EXISTS idx_burn_session_ts ON burn_events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_burn_project_ts ON burn_events(project_id, ts);
CREATE INDEX IF NOT EXISTS idx_burn_tool_ts    ON burn_events(tool_id, ts);

CREATE TABLE IF NOT EXISTS burn_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL
);
