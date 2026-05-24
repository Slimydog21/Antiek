"""Schema additions for the Deep Research Bridge."""

from __future__ import annotations

import os
import sys

import duckdb

try:
    from ...runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]


_KNOWN_SOURCES_SQL_LIST = "'chatgpt', 'anthropic', 'grok', 'alphasense', 'other'"


ANTIEK_RESEARCH_BRIDGE_SCHEMA_V1_SQL = f"""
CREATE TABLE IF NOT EXISTS research_pastes (
    document_id          TEXT PRIMARY KEY REFERENCES documents(document_id),
    source               TEXT NOT NULL CHECK (source IN ({_KNOWN_SOURCES_SQL_LIST})),
    source_confidence    REAL NOT NULL CHECK (source_confidence >= 0 AND source_confidence <= 1),
    raw_sha256           TEXT NOT NULL,
    paste_byte_length    INTEGER NOT NULL CHECK (paste_byte_length >= 0),
    parser_version       INTEGER NOT NULL DEFAULT 1,
    operator_label       TEXT,
    session_id           TEXT,
    pasted_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_pastes_source ON research_pastes(source);
CREATE INDEX IF NOT EXISTS idx_research_pastes_session ON research_pastes(session_id);
CREATE INDEX IF NOT EXISTS idx_research_pastes_sha ON research_pastes(raw_sha256);
CREATE INDEX IF NOT EXISTS idx_research_pastes_at ON research_pastes(pasted_at DESC);

CREATE TABLE IF NOT EXISTS research_paste_events (
    event_id              TEXT PRIMARY KEY,
    document_id           TEXT NOT NULL,
    occurred_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paste_byte_length     INTEGER NOT NULL,
    raw_sha256            TEXT NOT NULL,
    source                TEXT NOT NULL,
    call_site             TEXT NOT NULL DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_research_paste_events_doc ON research_paste_events(document_id);
CREATE INDEX IF NOT EXISTS idx_research_paste_events_at ON research_paste_events(occurred_at DESC);

CREATE TABLE IF NOT EXISTS research_paste_open_questions (
    question_id           TEXT PRIMARY KEY,
    document_id           TEXT NOT NULL REFERENCES documents(document_id),
    summary               TEXT NOT NULL,
    quote                 TEXT NOT NULL,
    quote_start_offset    INTEGER NOT NULL CHECK (quote_start_offset >= 0),
    quote_end_offset      INTEGER NOT NULL CHECK (quote_end_offset >= quote_start_offset),
    llm_confidence        REAL NOT NULL CHECK (llm_confidence >= 0 AND llm_confidence <= 1),
    extractor_version     INTEGER NOT NULL DEFAULT 1,
    model_id              TEXT NOT NULL,
    extracted_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paste_questions_doc ON research_paste_open_questions(document_id);
CREATE INDEX IF NOT EXISTS idx_paste_questions_version ON research_paste_open_questions(extractor_version);

CREATE TABLE IF NOT EXISTS research_paste_insights (
    insight_id            TEXT PRIMARY KEY,
    document_id           TEXT NOT NULL REFERENCES documents(document_id),
    summary               TEXT NOT NULL,
    quote                 TEXT NOT NULL,
    quote_start_offset    INTEGER NOT NULL CHECK (quote_start_offset >= 0),
    quote_end_offset      INTEGER NOT NULL CHECK (quote_end_offset >= quote_start_offset),
    llm_confidence        REAL NOT NULL CHECK (llm_confidence >= 0 AND llm_confidence <= 1),
    extractor_version     INTEGER NOT NULL DEFAULT 1,
    model_id              TEXT NOT NULL,
    promoted_node_id      TEXT,
    extracted_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paste_insights_doc ON research_paste_insights(document_id);
CREATE INDEX IF NOT EXISTS idx_paste_insights_version ON research_paste_insights(extractor_version);
CREATE INDEX IF NOT EXISTS idx_paste_insights_node ON research_paste_insights(promoted_node_id);

CREATE TABLE IF NOT EXISTS research_paste_extractions (
    extraction_id         TEXT PRIMARY KEY,
    document_id           TEXT NOT NULL,
    extractor_version     INTEGER NOT NULL,
    model_id              TEXT NOT NULL,
    started_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at           TIMESTAMP,
    status                TEXT NOT NULL CHECK (status IN ('ok', 'cache_hit', 'error')),
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cost_usd              REAL NOT NULL DEFAULT 0.0,
    insights_count        INTEGER NOT NULL DEFAULT 0,
    open_questions_count  INTEGER NOT NULL DEFAULT 0,
    quote_drops           INTEGER NOT NULL DEFAULT 0,
    error_message         TEXT
);
CREATE INDEX IF NOT EXISTS idx_paste_extractions_doc ON research_paste_extractions(document_id);
CREATE INDEX IF NOT EXISTS idx_paste_extractions_at ON research_paste_extractions(started_at DESC);

CREATE TABLE IF NOT EXISTS research_gap_runs (
    run_id              TEXT PRIMARY KEY,
    operator_label      TEXT,
    session_id          TEXT,
    scope_block_ids     TEXT NOT NULL,
    scope_question_ids  TEXT NOT NULL,
    cluster_model_id    TEXT NOT NULL,
    total_input_tokens  INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd      REAL NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gap_runs_session ON research_gap_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_gap_runs_at ON research_gap_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS research_gap_clusters (
    cluster_id     TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES research_gap_runs(run_id),
    label          TEXT NOT NULL,
    priority_rank  INTEGER NOT NULL CHECK (priority_rank >= 0),
    rationale      TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gap_clusters_run ON research_gap_clusters(run_id);
CREATE INDEX IF NOT EXISTS idx_gap_clusters_priority ON research_gap_clusters(priority_rank);

CREATE TABLE IF NOT EXISTS research_gap_cluster_questions (
    cluster_id        TEXT NOT NULL REFERENCES research_gap_clusters(cluster_id),
    question_id       TEXT NOT NULL REFERENCES research_paste_open_questions(question_id),
    order_index       INTEGER NOT NULL,
    PRIMARY KEY (cluster_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_gap_cq_question ON research_gap_cluster_questions(question_id);

CREATE TABLE IF NOT EXISTS research_gap_prompts (
    prompt_id                    TEXT PRIMARY KEY,
    run_id                       TEXT NOT NULL REFERENCES research_gap_runs(run_id),
    cluster_id                   TEXT REFERENCES research_gap_clusters(cluster_id),
    order_index                  INTEGER NOT NULL CHECK (order_index >= 0),
    prompt_text                  TEXT NOT NULL,
    target_provider              TEXT NOT NULL CHECK (target_provider IN ({_KNOWN_SOURCES_SQL_LIST})),
    expected_output_shape        TEXT,
    depends_on_prior_order_index INTEGER,
    rationale                    TEXT,
    input_tokens                 INTEGER NOT NULL DEFAULT 0,
    output_tokens                INTEGER NOT NULL DEFAULT 0,
    cost_usd                     REAL NOT NULL DEFAULT 0.0,
    created_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gap_prompts_run ON research_gap_prompts(run_id);
CREATE INDEX IF NOT EXISTS idx_gap_prompts_cluster ON research_gap_prompts(cluster_id);
CREATE INDEX IF NOT EXISTS idx_gap_prompts_order ON research_gap_prompts(run_id, order_index);

CREATE TABLE IF NOT EXISTS research_gap_prompt_answers (
    answer_id           TEXT PRIMARY KEY,
    prompt_id           TEXT NOT NULL REFERENCES research_gap_prompts(prompt_id),
    answer_document_id  TEXT NOT NULL,
    occurred_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gap_answers_prompt ON research_gap_prompt_answers(prompt_id);

CREATE TABLE IF NOT EXISTS research_gap_prompt_signals (
    signal_id       TEXT PRIMARY KEY,
    prompt_id       TEXT NOT NULL REFERENCES research_gap_prompts(prompt_id),
    signal_type     TEXT NOT NULL CHECK (signal_type IN ('would_run', 'skip')),
    occurred_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gap_signals_prompt ON research_gap_prompt_signals(prompt_id);
CREATE INDEX IF NOT EXISTS idx_gap_signals_at ON research_gap_prompt_signals(occurred_at DESC);
"""


def init_research_bridge(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "init_research_bridge requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write."
        )
    con.execute(ANTIEK_RESEARCH_BRIDGE_SCHEMA_V1_SQL)


def init_research_bridge_at_path(db_path: str) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="research_bridge_schema_init")
    try:
        init_research_bridge(con)
    finally:
        con.close()


def list_research_bridge_tables(con: "duckdb.DuckDBPyConnection") -> list[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' "
        "  AND (table_name LIKE 'research_paste%' "
        "       OR table_name LIKE 'research_gap%') "
        "ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]
