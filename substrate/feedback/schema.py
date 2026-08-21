"""Additive DuckDB schema for canonical artifact feedback state."""

from __future__ import annotations

from runtime.db_lock import LockedConnection

DDL = """
CREATE TABLE IF NOT EXISTS feedback_threads (
  thread_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  investigation_id VARCHAR NOT NULL,
  artifact_id VARCHAR NOT NULL,
  artifact_version INTEGER NOT NULL CHECK (artifact_version > 0),
  artifact_content_sha256 VARCHAR NOT NULL,
  artifact_source_sha256 VARCHAR NOT NULL,
  normalization VARCHAR NOT NULL CHECK (normalization = 'unicode-nfc-v1'),
  anchor_node_id VARCHAR NOT NULL,
  anchor_node_text_sha256 VARCHAR NOT NULL,
  anchor_start_scalar INTEGER NOT NULL CHECK (anchor_start_scalar >= 0),
  anchor_end_scalar INTEGER NOT NULL CHECK (anchor_end_scalar > anchor_start_scalar),
  anchor_quote VARCHAR NOT NULL,
  anchor_prefix VARCHAR NOT NULL,
  anchor_suffix VARCHAR NOT NULL,
  state VARCHAR NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'resolved')),
  create_operation_id VARCHAR NOT NULL UNIQUE,
  create_request_sha256 VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_work (
  work_id VARCHAR PRIMARY KEY,
  thread_id VARCHAR NOT NULL UNIQUE,
  logical_worker_id VARCHAR NOT NULL,
  state VARCHAR NOT NULL DEFAULT 'queued',
  context_sha256 VARCHAR NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  active_lease_id VARCHAR,
  lease_expires_at TIMESTAMPTZ,
  not_before TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_error_code VARCHAR,
  result_sha256 VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  terminal_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS feedback_items (
  item_id VARCHAR PRIMARY KEY,
  thread_id VARCHAR NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  author_kind VARCHAR NOT NULL CHECK (author_kind IN ('operator', 'agent', 'system')),
  author_id VARCHAR NOT NULL,
  body_markdown VARCHAR NOT NULL,
  work_id VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (thread_id, sequence)
);

CREATE TABLE IF NOT EXISTS agent_work_attempts (
  attempt_id VARCHAR PRIMARY KEY,
  work_id VARCHAR NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
  lease_id VARCHAR NOT NULL UNIQUE,
  bridge_credential_id VARCHAR NOT NULL,
  bridge_instance_id VARCHAR NOT NULL,
  state VARCHAR NOT NULL DEFAULT 'leased',
  lease_expires_at TIMESTAMPTZ NOT NULL,
  herdr_target_observed VARCHAR,
  adapter_version VARCHAR,
  result_from_state VARCHAR,
  submitted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (work_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS feedback_command_receipts (
  principal_id VARCHAR NOT NULL,
  command_kind VARCHAR NOT NULL,
  idempotency_key VARCHAR NOT NULL,
  request_sha256 VARCHAR NOT NULL,
  resource_id VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (principal_id, command_kind, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_feedback_threads_owner
  ON feedback_threads(owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_items_thread
  ON feedback_items(thread_id, sequence);
CREATE INDEX IF NOT EXISTS idx_agent_work_lease
  ON agent_work(logical_worker_id, state, not_before, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_work_attempts_work
  ON agent_work_attempts(work_id, attempt_no);
"""


def init_feedback_schema(con: LockedConnection) -> None:
    """Create the additive feedback schema on an existing writer connection."""
    con.execute(DDL)
