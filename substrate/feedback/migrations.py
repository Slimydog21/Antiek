"""D2 v41 feedback schema migration.

Ownership: SPR-01. This is the sole v40→v41 feedback migration entry point.
It uses one primary writer connection with per-phase durable transactions.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from runtime.db_lock import LockedConnection

MIGRATION_ID = "d2_feedback_v41"

# Table creation order matches the accepted D2 spec exactly.
V41_TABLE_ORDER: tuple[str, ...] = (
    "feedback_threads_v41",
    "feedback_items_v41",
    "agent_work_v41",
    "agent_work_attempts_v41",
    "feedback_threads_v41_quarantine",
    "feedback_items_v41_quarantine",
    "agent_work_v41_quarantine",
    "agent_work_attempts_v41_quarantine",
    "feedback_provenance",
)

# Baseline column arrays for copy.
FEEDBACK_THREADS_COLS: tuple[str, ...] = (
    "thread_id", "owner_user_id", "investigation_id", "artifact_id",
    "artifact_version", "artifact_content_sha256", "artifact_source_sha256",
    "normalization", "anchor_node_id", "anchor_node_text_sha256",
    "anchor_start_scalar", "anchor_end_scalar", "anchor_quote",
    "anchor_prefix", "anchor_suffix", "state", "create_operation_id",
    "create_request_sha256", "created_at", "updated_at",
)

FEEDBACK_ITEMS_COLS: tuple[str, ...] = (
    "item_id", "thread_id", "sequence", "author_kind", "author_id",
    "body_markdown", "work_id", "created_at",
)

AGENT_WORK_COLS: tuple[str, ...] = (
    "work_id", "thread_id", "logical_worker_id", "state", "context_sha256",
    "attempt_count", "active_lease_id", "lease_expires_at", "not_before",
    "last_error_code", "result_sha256", "created_at", "updated_at", "terminal_at",
)

AGENT_WORK_ATTEMPTS_COLS: tuple[str, ...] = (
    "attempt_id", "work_id", "attempt_no", "lease_id", "bridge_credential_id",
    "bridge_instance_id", "state", "lease_expires_at", "herdr_target_observed",
    "adapter_version", "transport_receipt_sha256", "result_from_state",
    "submitted_at", "acknowledged_at", "working_at", "completed_at", "created_at",
)

# Public names required by the D2 migration contract.  The map is the sole
# source/destination declaration used by the digest and copy code; no SELECT *.
FEEDBACK_V41_TABLE_ORDER = V41_TABLE_ORDER
FEEDBACK_V41_COLUMN_MAP: dict[str, dict[str, Any]] = {
    "feedback_threads_v41": {"source_table": "feedback_threads", "source_columns": FEEDBACK_THREADS_COLS,
        "defaults": {"entry_kind": "comment", "highlight_color": None, "resolution_event_id": None,
                      "branch_investigation_id": None, "branch_start_event_id": None}},
    "feedback_items_v41": {"source_table": "feedback_items", "source_columns": FEEDBACK_ITEMS_COLS,
        "defaults": {"entry_kind": "comment"}},
    "agent_work_v41": {"source_table": "agent_work", "source_columns": AGENT_WORK_COLS,
        "defaults": {"dispatch_id": None, "work_kind": "feedback_reply"}},
    "agent_work_attempts_v41": {"source_table": "agent_work_attempts", "source_columns": AGENT_WORK_ATTEMPTS_COLS,
        "defaults": {"dispatch_id": None, "work_kind": "feedback_reply", "attempt_actual_cents": 0,
                      "provider_boundary_crossed": False, "provider_receipt_sha256": None,
                      "provider_result_json": None, "provider_result_sha256": None, "evidence_sha256": None}},
    "feedback_threads_v41_quarantine": {"source_table": None, "source_columns":
        ("quarantine_id", "original_thread_id", "reason", "original_row_sha256", "evidence_json", "quarantined_at")},
    "feedback_items_v41_quarantine": {"source_table": None, "source_columns":
        ("quarantine_id", "original_item_id", "original_thread_id", "reason", "original_row_sha256", "evidence_json", "quarantined_at")},
    "agent_work_v41_quarantine": {"source_table": None, "source_columns":
        ("quarantine_id", "original_work_id", "reason", "original_row_sha256", "evidence_json", "quarantined_at")},
    "agent_work_attempts_v41_quarantine": {"source_table": None, "source_columns":
        ("quarantine_id", "original_attempt_id", "original_work_id", "reason", "original_row_sha256", "evidence_json", "quarantined_at")},
    "feedback_provenance": {"source_table": None, "source_columns":
        ("thread_id", "owner_user_id", "ref_index", "node_id", "edge_id", "chunk_id", "claim_id", "document_id",
         "ip_holder_id", "status", "holder_status", "reason", "source_digest_sha256", "created_at")},
}

# Destination order and validation metadata are explicit so callers and tests can
# audit the migration contract without parsing INSERT statements.
FEEDBACK_V41_COLUMN_MAP["feedback_threads_v41"].update({
    "destination_columns": ("thread_id", "owner_user_id", "investigation_id", "artifact_id", "artifact_version",
        "artifact_content_sha256", "artifact_source_sha256", "normalization", "anchor_node_id",
        "anchor_node_text_sha256", "anchor_start_scalar", "anchor_end_scalar", "anchor_quote", "anchor_prefix",
        "anchor_suffix", "state", "create_operation_id", "create_request_sha256", "entry_kind", "highlight_color",
        "resolution_event_id", "branch_investigation_id", "branch_start_event_id", "created_at", "updated_at"),
    "default_expressions": {"entry_kind": "'comment'", "highlight_color": "NULL", "resolution_event_id": "NULL",
        "branch_investigation_id": "NULL", "branch_start_event_id": "NULL"},
    "validation_predicates": {"hashes": "lower-case 64-hex", "normalization": "unicode-nfc-v1",
        "lifecycle": "state/resolution pointers are coherent"},
    "quarantine_reason_mapping": {"shape": "invalid_shape", "hash": "invalid_hash", "anchor": "invalid_anchor",
        "lifecycle": "invalid_lifecycle"},
})
FEEDBACK_V41_COLUMN_MAP["feedback_items_v41"].update({
    "destination_columns": ("item_id", "thread_id", "sequence", "author_kind", "author_id", "entry_kind",
        "body_markdown", "work_id", "created_at"),
    "default_expressions": {"entry_kind": "'comment'"},
    "validation_predicates": {"author_kind": "operator|agent|system", "body_markdown": "1..32768 bytes",
        "parent": "active thread"},
    "quarantine_reason_mapping": {"shape": "invalid_shape", "author": "invalid_author", "body": "invalid_body",
        "correlation": "invalid_correlation", "parent": "missing_parent"},
})
FEEDBACK_V41_COLUMN_MAP["agent_work_v41"].update({
    "destination_columns": ("work_id", "thread_id", "logical_worker_id", "state", "context_sha256", "attempt_count",
        "active_lease_id", "lease_expires_at", "not_before", "last_error_code", "result_sha256", "created_at",
        "updated_at", "terminal_at", "dispatch_id", "work_kind"),
    "default_expressions": {"dispatch_id": "NULL", "work_kind": "'feedback_reply'"},
    "validation_predicates": {"state": "v40 feedback states", "correlation": "active thread", "attempt_count": ">=0"},
    "quarantine_reason_mapping": {"state": "invalid_state", "attempt_count": "attempt_count_exceeded",
        "correlation": "invalid_correlation"},
})
FEEDBACK_V41_COLUMN_MAP["agent_work_attempts_v41"].update({
    "destination_columns": ("attempt_id", "work_id", "attempt_no", "lease_id", "bridge_credential_id", "bridge_instance_id",
        "state", "lease_expires_at", "herdr_target_observed", "adapter_version", "transport_receipt_sha256",
        "result_from_state", "submitted_at", "acknowledged_at", "working_at", "completed_at", "created_at",
        "dispatch_id", "work_kind", "attempt_actual_cents", "provider_boundary_crossed", "provider_receipt_sha256",
        "provider_result_json", "provider_result_sha256", "evidence_sha256"),
    "default_expressions": {"dispatch_id": "NULL", "work_kind": "'feedback_reply'", "attempt_actual_cents": "0",
        "provider_boundary_crossed": "false", "provider_receipt_sha256": "NULL", "provider_result_json": "NULL",
        "provider_result_sha256": "NULL", "evidence_sha256": "NULL"},
    "validation_predicates": {"attempt_no": ">0", "correlation": "active work", "state": "v40 attempt states"},
    "quarantine_reason_mapping": {"state": "invalid_state", "attempt_no": "invalid_attempt_no",
        "correlation": "invalid_correlation"},
})


def _source_columns(table: str) -> tuple[str, ...]:
    return tuple(FEEDBACK_V41_COLUMN_MAP[table]["source_columns"])


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_row_json(row: dict[str, Any], columns: Sequence[str]) -> bytes:
    """Encode named row fields deterministically for migration evidence."""
    import unicodedata
    obj: dict[str, Any] = {}
    for col in columns:
        val = row.get(col)
        if val is None or isinstance(val, (bool, int, float)):
            obj[col] = val
        elif isinstance(val, datetime):
            timestamp = val if val.tzinfo is not None else val.replace(tzinfo=UTC)
            obj[col] = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
        elif isinstance(val, bytes):
            obj[col] = unicodedata.normalize("NFC", val.decode("utf-8", errors="replace"))
        else:
            obj[col] = unicodedata.normalize("NFC", str(val))
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def schema_digest(table_ddls: dict[str, str]) -> str:
    """SHA-256 of canonical JSON of ordered table DDL."""
    items = [{"table": name, "ddl": table_ddls[name]} for name in V41_TABLE_ORDER]
    blob = json.dumps(items, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return _sha256(blob)


_CANONICAL_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "feedback_threads_v41": ("thread_id",),
    "feedback_items_v41": ("item_id",),
    "agent_work_v41": ("work_id",),
    "agent_work_attempts_v41": ("attempt_id",),
    "feedback_threads_v41_quarantine": ("quarantine_id",),
    "feedback_items_v41_quarantine": ("quarantine_id",),
    "agent_work_v41_quarantine": ("quarantine_id",),
    "agent_work_attempts_v41_quarantine": ("quarantine_id",),
    "feedback_provenance": ("thread_id", "ref_index"),
}


def row_digest(
    rows_by_table: dict[str, list[dict[str, Any]]],
    columns_by_table: dict[str, tuple[str, ...]],
    pk: str | None = None,
) -> str:
    """Hash canonical rows in table order, sorted by each table's key.

    ``pk`` is retained for callers of the original helper.  Migration code
    passes ``None`` so every table uses its first declared key column.
    """
    parts = []
    for table in V41_TABLE_ORDER:
        cols = columns_by_table[table]
        keys = (pk,) if pk is not None and pk in cols else _CANONICAL_PRIMARY_KEYS.get(table, (cols[0],))
        rows = sorted(rows_by_table.get(table, []), key=lambda r: tuple(str(r.get(key, "")) for key in keys))
        parts.append({"table": table, "rows": [json.loads(canonical_row_json(r, cols)) for r in rows]})
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    return _sha256(blob)


def _canonical_schema_ddls() -> dict[str, str]:
    """Extract the nine canonical CREATE statements from the D2 DDL."""
    ddl = _get_v41_ddl()
    matches = list(re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) ", ddl))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(ddl)
        statement = ddl[match.start():end].strip()
        result[match.group(1)] = " ".join(statement.split())
    return result


def _actual_schema_ddls(con: LockedConnection, *, active: bool) -> dict[str, str]:
    """Read actual DDL and normalize renamed active table names."""
    names = {name: name for name in V41_TABLE_ORDER}
    if active:
        for name in ("feedback_threads_v41", "feedback_items_v41", "agent_work_v41", "agent_work_attempts_v41"):
            names[name] = name.replace("_v41", "")
    result: dict[str, str] = {}
    for canonical, actual in names.items():
        row = con.execute("SELECT sql FROM sqlite_master WHERE name = ?", [actual]).fetchone()
        if row is None or not row[0]:
            raise RuntimeError(f"migration_conflict: schema table {actual} missing")
        sql = " ".join(str(row[0]).split())
        sql = re.sub(rf"\b{re.escape(actual)}\b", canonical, sql, count=1)
        result[canonical] = sql
    return result


def _table_rows(con: LockedConnection, table: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    names = ", ".join(columns)
    return [dict(zip(columns, row, strict=True)) for row in con.execute(f"SELECT {names} FROM {table}").fetchall()]


def _migration_digests(con: LockedConnection, *, active: bool) -> tuple[str, str]:
    """Compute schema and row digests from the tables currently on disk."""
    actual_names = {name: name for name in V41_TABLE_ORDER}
    if active:
        for name in ("feedback_threads_v41", "feedback_items_v41", "agent_work_v41", "agent_work_attempts_v41"):
            actual_names[name] = name.replace("_v41", "")
    columns: dict[str, tuple[str, ...]] = {}
    for name in V41_TABLE_ORDER:
        actual = actual_names[name]
        column_rows = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", [actual]
        ).fetchall()
        if not column_rows:
            raise RuntimeError(f"migration_conflict: columns for {actual} missing")
        columns[name] = tuple(str(row[0]) for row in column_rows)
    rows = {name: _table_rows(con, actual_names[name], columns[name]) for name in V41_TABLE_ORDER}
    return schema_digest(_actual_schema_ddls(con, active=active)), row_digest(rows, columns)


def _get_v41_ddl() -> str:
    """Return the full v41 CREATE TABLE DDL from the spec."""
    return """
CREATE TABLE IF NOT EXISTS feedback_threads_v41 (
  thread_id VARCHAR PRIMARY KEY CHECK(regexp_matches(thread_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  owner_user_id VARCHAR NOT NULL CHECK(regexp_matches(owner_user_id,'^[\x20-\x7e]{1,256}$')),
  investigation_id VARCHAR NOT NULL CHECK(regexp_matches(investigation_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  artifact_id VARCHAR NOT NULL CHECK(regexp_matches(artifact_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  artifact_version INTEGER NOT NULL CHECK(artifact_version > 0),
  artifact_content_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(artifact_content_sha256,'^[0-9a-f]{64}$')),
  artifact_source_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(artifact_source_sha256,'^[0-9a-f]{64}$')),
  normalization VARCHAR NOT NULL CHECK(normalization = 'unicode-nfc-v1'),
  anchor_node_id VARCHAR NOT NULL CHECK(regexp_matches(anchor_node_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  anchor_node_text_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(anchor_node_text_sha256,'^[0-9a-f]{64}$')),
  anchor_start_scalar INTEGER NOT NULL CHECK(anchor_start_scalar >= 0),
  anchor_end_scalar INTEGER NOT NULL CHECK(anchor_end_scalar > anchor_start_scalar),
  anchor_quote VARCHAR NOT NULL CHECK(length(anchor_quote) BETWEEN 1 AND 4096),
  anchor_prefix VARCHAR NOT NULL CHECK(length(anchor_prefix) BETWEEN 0 AND 32),
  anchor_suffix VARCHAR NOT NULL CHECK(length(anchor_suffix) BETWEEN 0 AND 32),
  state VARCHAR NOT NULL DEFAULT 'open' CHECK(state IN ('open','resolved')),
  create_operation_id VARCHAR NOT NULL UNIQUE CHECK(regexp_matches(create_operation_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  create_request_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(create_request_sha256,'^[0-9a-f]{64}$')),
  entry_kind VARCHAR NOT NULL DEFAULT 'comment' CHECK(entry_kind IN ('comment','highlight')),
  highlight_color VARCHAR NULL CHECK(highlight_color IS NULL OR highlight_color IN ('essential','supporting','disputed','question','agent')),
  resolution_event_id VARCHAR NULL CHECK(resolution_event_id IS NULL OR regexp_matches(resolution_event_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  branch_investigation_id VARCHAR NULL CHECK(branch_investigation_id IS NULL OR regexp_matches(branch_investigation_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  branch_start_event_id VARCHAR NULL CHECK(branch_start_event_id IS NULL OR regexp_matches(branch_start_event_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK((entry_kind = 'comment' AND highlight_color IS NULL OR entry_kind = 'highlight' AND highlight_color IS NOT NULL) IS TRUE),
  CHECK((state = 'open' AND resolution_event_id IS NULL OR state = 'resolved' AND resolution_event_id IS NOT NULL) IS TRUE),
  CHECK(((branch_investigation_id IS NULL) = (branch_start_event_id IS NULL)) IS TRUE),
  CHECK((state <> 'resolved' OR (branch_investigation_id IS NULL AND branch_start_event_id IS NULL)) IS TRUE),
  CHECK((state <> 'open' OR resolution_event_id IS NULL) IS TRUE)
);
CREATE TABLE IF NOT EXISTS feedback_items_v41 (
  item_id VARCHAR PRIMARY KEY CHECK(regexp_matches(item_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  thread_id VARCHAR NOT NULL CHECK(regexp_matches(thread_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  sequence INTEGER NOT NULL CHECK(sequence > 0),
  author_kind VARCHAR NOT NULL CHECK(author_kind IN ('operator','agent','system')),
  author_id VARCHAR NOT NULL CHECK(regexp_matches(author_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  entry_kind VARCHAR NOT NULL CHECK(entry_kind IN ('comment','highlight')),
  body_markdown VARCHAR NOT NULL CHECK(length(body_markdown) BETWEEN 0 AND 32768),
  work_id VARCHAR NULL CHECK(work_id IS NULL OR regexp_matches(work_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(thread_id,sequence),
  CHECK((entry_kind = 'comment' AND length(body_markdown) BETWEEN 1 AND 32768 OR entry_kind = 'highlight' AND length(body_markdown) BETWEEN 0 AND 32768) IS TRUE)
);
CREATE TABLE IF NOT EXISTS agent_work_v41 (
  work_id VARCHAR PRIMARY KEY CHECK(regexp_matches(work_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  thread_id VARCHAR NOT NULL UNIQUE CHECK(regexp_matches(thread_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  logical_worker_id VARCHAR NOT NULL CHECK(length(logical_worker_id) BETWEEN 1 AND 256),
  state VARCHAR NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','leased','submitted','acknowledged','working','replied','declined','approval_requested','failed','sent','provider_unknown','validation_retry','settlement_pending','completed','cancelled','lease_expired','retryable_failure')),
  context_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(context_sha256,'^[0-9a-f]{64}$')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
  active_lease_id VARCHAR NULL CHECK(active_lease_id IS NULL OR regexp_matches(active_lease_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  lease_expires_at TIMESTAMPTZ NULL,
  not_before TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_error_code VARCHAR NULL,
  result_sha256 CHAR(64) NULL CHECK(result_sha256 IS NULL OR regexp_matches(result_sha256,'^[0-9a-f]{64}$')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  terminal_at TIMESTAMPTZ NULL,
  dispatch_id VARCHAR NULL CHECK(dispatch_id IS NULL OR regexp_matches(dispatch_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  work_kind VARCHAR NOT NULL DEFAULT 'feedback_reply' CHECK(work_kind IN ('feedback_reply','feedback_dispatch')),
  CHECK((work_kind = 'feedback_reply') = (dispatch_id IS NULL) IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR attempt_count BETWEEN 0 AND 2) IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR state <> 'cancelled') IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR last_error_code IS NULL OR last_error_code IN ('provider_result_missing','authority_receipt_mismatch','owner_child_failed','publication_recovery_required','budget_exceeded','provider_call_failed','invalid_command_result')) IS TRUE)
);
CREATE TABLE IF NOT EXISTS agent_work_attempts_v41 (
  attempt_id VARCHAR PRIMARY KEY CHECK(regexp_matches(attempt_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  work_id VARCHAR NOT NULL CHECK(regexp_matches(work_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  attempt_no INTEGER NOT NULL CHECK(attempt_no > 0),
  lease_id VARCHAR NOT NULL UNIQUE CHECK(regexp_matches(lease_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  bridge_credential_id VARCHAR NOT NULL CHECK(regexp_matches(bridge_credential_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  bridge_instance_id VARCHAR NOT NULL CHECK(regexp_matches(bridge_instance_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  state VARCHAR NOT NULL DEFAULT 'leased' CHECK(state IN ('leased','submitted','acknowledged','working','completed','failed','sent','provider_unknown','validation_retry','settlement_pending','cancelled','lease_expired','retryable_failure')),
  lease_expires_at TIMESTAMPTZ NOT NULL,
  herdr_target_observed VARCHAR NULL,
  adapter_version VARCHAR NULL,
  transport_receipt_sha256 VARCHAR NULL,
  result_from_state VARCHAR NULL,
  submitted_at TIMESTAMPTZ NULL,
  acknowledged_at TIMESTAMPTZ NULL,
  working_at TIMESTAMPTZ NULL,
  completed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  dispatch_id VARCHAR NULL CHECK(dispatch_id IS NULL OR regexp_matches(dispatch_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  work_kind VARCHAR NOT NULL DEFAULT 'feedback_reply' CHECK(work_kind IN ('feedback_reply','feedback_dispatch')),
  attempt_actual_cents BIGINT NULL CHECK(attempt_actual_cents IS NULL OR attempt_actual_cents >= 0),
  provider_boundary_crossed BOOLEAN NOT NULL DEFAULT false,
  provider_receipt_sha256 CHAR(64) NULL CHECK(provider_receipt_sha256 IS NULL OR regexp_matches(provider_receipt_sha256,'^[0-9a-f]{64}$')),
  provider_result_json VARCHAR NULL CHECK(provider_result_json IS NULL OR octet_length(encode(provider_result_json)) <= 32768),
  provider_result_sha256 CHAR(64) NULL CHECK(provider_result_sha256 IS NULL OR regexp_matches(provider_result_sha256,'^[0-9a-f]{64}$')),
  evidence_sha256 CHAR(64) NULL CHECK(evidence_sha256 IS NULL OR regexp_matches(evidence_sha256,'^[0-9a-f]{64}$')),
  UNIQUE(work_id,attempt_no),
  CHECK((provider_result_json IS NULL OR provider_result_sha256 = sha256(provider_result_json)) IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR state <> 'cancelled' OR (provider_boundary_crossed = false AND provider_receipt_sha256 IS NULL AND provider_result_json IS NULL AND provider_result_sha256 IS NULL AND evidence_sha256 IS NULL AND attempt_actual_cents = 0)) IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR state <> 'failed' OR (provider_boundary_crossed = true AND provider_receipt_sha256 IS NOT NULL AND evidence_sha256 IS NOT NULL AND attempt_actual_cents >= 0)) IS TRUE),
  CHECK((work_kind <> 'feedback_dispatch' OR state <> 'provider_unknown' OR (attempt_actual_cents IS NULL AND provider_receipt_sha256 IS NULL AND provider_result_json IS NULL AND provider_result_sha256 IS NULL AND evidence_sha256 IS NULL)) IS TRUE),
  CHECK((state NOT IN ('sent','provider_unknown','settlement_pending','completed','failed') OR provider_boundary_crossed = true) IS TRUE),
  CHECK((state NOT IN ('settlement_pending','completed') OR (provider_result_sha256 IS NOT NULL AND provider_receipt_sha256 IS NOT NULL AND evidence_sha256 IS NOT NULL)) IS TRUE),
  CHECK((state <> 'completed' OR provider_result_sha256 IS NOT NULL) IS TRUE),
  CHECK((((provider_result_json IS NULL) = (provider_result_sha256 IS NULL))) IS TRUE)
);
CREATE TABLE IF NOT EXISTS feedback_threads_v41_quarantine (
  quarantine_id VARCHAR PRIMARY KEY CHECK(regexp_matches(quarantine_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  original_thread_id VARCHAR NULL CHECK(original_thread_id IS NULL OR octet_length(encode(original_thread_id)) <= 256),
  reason VARCHAR NOT NULL CHECK(reason IN ('invalid_shape','invalid_hash','invalid_anchor','invalid_lifecycle','unknown_malformation')),
  original_row_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(original_row_sha256,'^[0-9a-f]{64}$')),
  evidence_json VARCHAR NOT NULL CHECK(octet_length(encode(evidence_json)) <= 8192),
  quarantined_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_items_v41_quarantine (
  quarantine_id VARCHAR PRIMARY KEY CHECK(regexp_matches(quarantine_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  original_item_id VARCHAR NULL CHECK(original_item_id IS NULL OR octet_length(encode(original_item_id)) <= 256),
  original_thread_id VARCHAR NULL CHECK(original_thread_id IS NULL OR octet_length(encode(original_thread_id)) <= 256),
  reason VARCHAR NOT NULL CHECK(reason IN ('invalid_shape','invalid_author','invalid_body','invalid_correlation','missing_parent','unknown_malformation')),
  original_row_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(original_row_sha256,'^[0-9a-f]{64}$')),
  evidence_json VARCHAR NOT NULL CHECK(octet_length(encode(evidence_json)) <= 8192),
  quarantined_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_work_v41_quarantine (
  quarantine_id VARCHAR PRIMARY KEY CHECK(regexp_matches(quarantine_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  original_work_id VARCHAR NULL CHECK(original_work_id IS NULL OR octet_length(encode(original_work_id)) <= 256),
  reason VARCHAR NOT NULL CHECK(reason IN ('invalid_state','attempt_count_exceeded','invalid_correlation','unknown_malformation')),
  original_row_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(original_row_sha256,'^[0-9a-f]{64}$')),
  evidence_json VARCHAR NOT NULL CHECK(octet_length(encode(evidence_json)) <= 8192),
  quarantined_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_work_attempts_v41_quarantine (
  quarantine_id VARCHAR PRIMARY KEY CHECK(regexp_matches(quarantine_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  original_attempt_id VARCHAR NULL CHECK(original_attempt_id IS NULL OR octet_length(encode(original_attempt_id)) <= 256),
  original_work_id VARCHAR NULL CHECK(original_work_id IS NULL OR octet_length(encode(original_work_id)) <= 256),
  reason VARCHAR NOT NULL CHECK(reason IN ('invalid_state','invalid_attempt_no','invalid_correlation','unknown_malformation')),
  original_row_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(original_row_sha256,'^[0-9a-f]{64}$')),
  evidence_json VARCHAR NOT NULL CHECK(octet_length(encode(evidence_json)) <= 8192),
  quarantined_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_provenance (
  thread_id VARCHAR NOT NULL CHECK(regexp_matches(thread_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  owner_user_id VARCHAR NOT NULL CHECK(regexp_matches(owner_user_id,'^[\x20-\x7e]{1,256}$')),
  ref_index INTEGER NOT NULL CHECK(ref_index BETWEEN 0 AND 7),
  node_id VARCHAR NOT NULL CHECK(regexp_matches(node_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  edge_id VARCHAR NULL CHECK(edge_id IS NULL OR regexp_matches(edge_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  chunk_id VARCHAR NULL CHECK(chunk_id IS NULL OR regexp_matches(chunk_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  claim_id VARCHAR NULL CHECK(claim_id IS NULL OR regexp_matches(claim_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  document_id VARCHAR NULL CHECK(document_id IS NULL OR regexp_matches(document_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  ip_holder_id VARCHAR NULL CHECK(ip_holder_id IS NULL OR regexp_matches(ip_holder_id,'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')),
  status VARCHAR NOT NULL CHECK(status IN ('resolved','dangling','quarantined')),
  holder_status VARCHAR NULL CHECK(holder_status IS NULL OR holder_status IN ('pre_onboarded','invited','claimed','opted_out')),
  reason VARCHAR NOT NULL CHECK(reason IN ('missing_edge','missing_chunk','missing_document','missing_holder','owner_mismatch','unsupported_source','ambiguous','ok')),
  source_digest_sha256 CHAR(64) NOT NULL CHECK(regexp_matches(source_digest_sha256,'^[0-9a-f]{64}$')),
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(thread_id,ref_index),
  CHECK((status <> 'resolved' OR (reason = 'ok' AND edge_id IS NOT NULL AND chunk_id IS NOT NULL AND document_id IS NOT NULL AND ip_holder_id IS NOT NULL AND holder_status IS NOT NULL)) IS TRUE),
  CHECK((status <> 'resolved' OR reason = 'ok') IS TRUE),
  CHECK((reason <> 'ok' OR status = 'resolved') IS TRUE),
  CHECK((status <> 'dangling' OR reason <> 'ok') IS TRUE),
  CHECK((status <> 'quarantined' OR reason <> 'ok') IS TRUE)
);
"""


def _get_schema_migrations_ddl() -> str:
    return """
CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_id VARCHAR PRIMARY KEY CHECK(migration_id IN ('d2_feedback_v41','d2_research_artifact_versions_v41')),
  phase VARCHAR NOT NULL CHECK(phase IN ('started','temp_created','copied','renamed','completed')),
  temp_schema_sha256 CHAR(64) NULL CHECK(temp_schema_sha256 IS NULL OR regexp_matches(temp_schema_sha256,'^[0-9a-f]{64}$')),
  temp_rows_sha256 CHAR(64) NULL CHECK(temp_rows_sha256 IS NULL OR regexp_matches(temp_rows_sha256,'^[0-9a-f]{64}$')),
  active_schema_sha256 CHAR(64) NULL CHECK(active_schema_sha256 IS NULL OR regexp_matches(active_schema_sha256,'^[0-9a-f]{64}$')),
  active_rows_sha256 CHAR(64) NULL CHECK(active_rows_sha256 IS NULL OR regexp_matches(active_rows_sha256,'^[0-9a-f]{64}$')),
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ NULL,
  CHECK((phase = 'completed') = (completed_at IS NOT NULL)),
  CHECK((phase NOT IN ('copied','renamed','completed') OR (temp_schema_sha256 IS NOT NULL AND temp_rows_sha256 IS NOT NULL)) IS TRUE),
  CHECK((phase <> 'completed' OR (temp_schema_sha256 IS NOT NULL AND temp_rows_sha256 IS NOT NULL AND active_schema_sha256 IS NOT NULL AND active_rows_sha256 IS NOT NULL)) IS TRUE)
);
"""


def _q_id(table: str, original_row_sha256: str) -> str:
    """Deterministic quarantine key."""
    return f"q_{_sha256(f'd2-quarantine\0{table}\0{original_row_sha256}'.encode())}"


_PROCESS_MIGRATION_LOCK = threading.Lock()


@contextlib.contextmanager
def _migration_lock(con: LockedConnection):
    """Take the migration-specific lock before touching catalog or marker."""
    db_path = getattr(con, "_db_path", "")
    fd: int | None = None
    process_lock = _PROCESS_MIGRATION_LOCK
    if db_path:
        lock_path = f"{db_path}.d2_feedback_v41.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise RuntimeError("migration_in_progress: d2_feedback_v41") from exc
    elif not process_lock.acquire(blocking=False):
        raise RuntimeError("migration_in_progress: d2_feedback_v41")
    try:
        yield
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        else:
            process_lock.release()


def _bounded_text(value: Any, limit: int = 256) -> str | None:
    if value is None:
        return None
    raw = str(value).encode("utf-8")[:limit]
    return raw.decode("utf-8", errors="ignore")


def _evidence(fields: dict[str, Any], reason: str) -> str:
    safe = {"truncated_fields": {}}
    for key, value in fields.items():
        text = _bounded_text(value, 512)
        safe["truncated_fields"][key] = text
    safe["reason"] = reason
    encoded = json.dumps(safe, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return encoded.encode("utf-8")[:8192].decode("utf-8", errors="ignore")


@contextlib.contextmanager
def _phase_transaction(con: LockedConnection):
    """Make each durable migration phase one primary-connection transaction."""
    con.execute("BEGIN")
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def _cas_phase(con: LockedConnection, expected: str, new: str, **values: Any) -> None:
    """Advance the marker only from the expected committed phase."""
    assignments = ["phase = ?"]
    params: list[Any] = [new]
    for key, value in values.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    params.extend([MIGRATION_ID, expected])
    con.execute(
        f"UPDATE schema_migrations SET {', '.join(assignments)} "
        "WHERE migration_id = ? AND phase = ?",
        params,
    )
    row = con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = ?", [MIGRATION_ID]
    ).fetchone()
    if row is None or row[0] != new:
        raise RuntimeError(f"migration_conflict: expected phase {expected!r}, found {row[0] if row else None!r}")


def migrate_feedback_v41(con: LockedConnection) -> None:
    """Run the v40→v41 feedback migration with per-phase durability.

    Uses one primary writer connection. Each phase commits separately.
    Crash resume picks up from the committed phase marker.
    """
    with _migration_lock(con):
        # Phase 1: create/read marker before validating only a non-completed baseline.
        con.execute(_get_schema_migrations_ddl())
        existing = con.execute(
            "SELECT phase, temp_schema_sha256, temp_rows_sha256, active_schema_sha256, active_rows_sha256 "
            "FROM schema_migrations WHERE migration_id = ?", [MIGRATION_ID]
        ).fetchone()

        if existing:
            phase = str(existing[0])
            if phase == "completed":
                # Verify active shape and both committed digests.
                _verify_active_shape(con, expected_schema=existing[3], expected_rows=existing[4])
                return
            # Resume from existing phase.
            _validate_baseline_shape(con)
            _resume_from_phase(con, phase, existing)
            return

        _validate_baseline_shape(con)
        # Insert marker as started.
        con.execute(
            "INSERT INTO schema_migrations (migration_id, phase, started_at) VALUES (?, 'started', ?)",
            [MIGRATION_ID, _now_utc()]
        )

        # Phase 2: Create v41 tables and set temp_created.
        _phase_create_tables(con, expected="started")

        # Phase 3: Copy rows and set copied.
        _phase_copy_rows(con, expected="temp_created")

        # Phase 4: Rename tables and set renamed.
        _phase_rename(con, expected="copied")

        # Phase 5: Complete marker.
        _phase_complete(con, expected="renamed")


def _validate_baseline_shape(con: LockedConnection) -> None:
    """Fail closed before any marker/catalog mutation on a non-v41 baseline."""
    expected = {
        "feedback_threads": FEEDBACK_THREADS_COLS,
        "feedback_items": FEEDBACK_ITEMS_COLS,
        "agent_work": AGENT_WORK_COLS,
        "agent_work_attempts": AGENT_WORK_ATTEMPTS_COLS,
    }
    for table, columns in expected.items():
        found = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? "
            "ORDER BY ordinal_position", [table]
        ).fetchall()
        actual = tuple(str(row[0]) for row in found)
        if actual != columns:
            raise RuntimeError(f"migration_conflict: baseline shape mismatch for {table}")


def _verify_active_shape(con: LockedConnection, *, expected_schema: str | None = None, expected_rows: str | None = None) -> None:
    """Verify active v41 tables exist with expected schema.

    After rename, the four active tables have baseline names:
    feedback_threads, feedback_items, agent_work, agent_work_attempts.
    The four quarantine tables and feedback_provenance keep their v41 names.
    """
    active_names = [
        "feedback_threads", "feedback_items", "agent_work", "agent_work_attempts",
        "feedback_threads_v41_quarantine", "feedback_items_v41_quarantine",
        "agent_work_v41_quarantine", "agent_work_attempts_v41_quarantine",
        "feedback_provenance",
    ]
    for table in active_names:
        result = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()
        if result is None:
            raise RuntimeError(f"migration_conflict: active table {table} missing after completed marker")
    if expected_schema is not None and expected_rows is not None:
        actual_schema, actual_rows = _migration_digests(con, active=True)
        if (actual_schema, actual_rows) != (expected_schema, expected_rows):
            raise RuntimeError("migration_conflict: active schema/row digest mismatch")


def _resume_from_phase(con: LockedConnection, phase: str, marker_row: tuple) -> None:
    """Resume only from a committed marker phase, after digest validation."""
    if phase == "started":
        _phase_create_tables(con, expected="started")
        _phase_copy_rows(con, expected="temp_created")
        _phase_rename(con, expected="copied")
        _phase_complete(con, expected="renamed")
    elif phase == "temp_created":
        _verify_temp_exists(con)
        _phase_copy_rows(con, expected="temp_created")
        _phase_rename(con, expected="copied")
        _phase_complete(con, expected="renamed")
    elif phase == "copied":
        _verify_temp_row_digests(con, marker_row[1], marker_row[2])
        _phase_rename(con, expected="copied")
        _phase_complete(con, expected="renamed")
    elif phase == "renamed":
        _phase_complete(con, expected="renamed")
    else:
        raise RuntimeError(f"migration_conflict: unknown phase {phase!r}")


def _verify_temp_exists(con: LockedConnection) -> None:
    """Verify all v41 temp tables exist."""
    for table in V41_TABLE_ORDER:
        result = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()
        if result is None:
            raise RuntimeError(f"migration_conflict: temp table {table} missing")


def _verify_temp_row_digests(con: LockedConnection, expected_schema: str, expected_rows: str) -> None:
    """Verify both canonical temp digests before rename/resume."""
    _verify_temp_exists(con)
    actual_schema, actual_rows = _migration_digests(con, active=False)
    if (actual_schema, actual_rows) != (expected_schema, expected_rows):
        raise RuntimeError("migration_conflict: temporary schema/row digest mismatch")


def _phase_create_tables(con: LockedConnection, *, expected: str) -> None:
    """Create all nine v41 tables."""
    with _phase_transaction(con):
        con.execute(_get_v41_ddl())
        _cas_phase(con, expected, "temp_created", started_at=_now_utc())


def _phase_copy_rows(con: LockedConnection, *, expected: str) -> None:
    """Copy baseline rows to v41 tables with quarantine."""
    with _phase_transaction(con):
        now = _now_utc()
        _copy_threads(con, now)
        _copy_items(con, now)
        _copy_work(con, now)
        _copy_attempts(con, now)
        _apply_dependency_cascade(con, now)
        temp_schema_sha, temp_rows_sha = _migration_digests(con, active=False)
        _cas_phase(
            con, expected, "copied",
            temp_schema_sha256=temp_schema_sha,
            temp_rows_sha256=temp_rows_sha,
        )


def _copy_threads(con: LockedConnection, now: datetime) -> None:
    """Copy feedback_threads to v41 with validation and quarantine."""
    baseline_cols = ", ".join(_source_columns("feedback_threads_v41"))
    rows = con.execute(f"SELECT {baseline_cols} FROM feedback_threads").fetchall()
    col_names = _source_columns("feedback_threads_v41")

    for row in rows:
        row_dict = dict(zip(col_names, row, strict=False))
        # Validate: check key fields.
        thread_id = row_dict.get("thread_id", "")
        owner_user_id = row_dict.get("owner_user_id", "")
        row_dict.get("investigation_id", "")
        row_dict.get("artifact_id", "")
        artifact_content_sha256 = row_dict.get("artifact_content_sha256", "")
        artifact_source_sha256 = row_dict.get("artifact_source_sha256", "")
        anchor_quote = row_dict.get("anchor_quote", "")
        anchor_prefix = row_dict.get("anchor_prefix", "")
        anchor_suffix = row_dict.get("anchor_suffix", "")
        row_dict.get("create_operation_id", "")
        row_dict.get("create_request_sha256", "")

        # Basic validation.
        is_valid = True
        reason = "unknown_malformation"

        if not thread_id or len(thread_id) > 256 or not owner_user_id or len(owner_user_id) > 256:
            is_valid = False
            reason = "invalid_shape"
        elif not artifact_content_sha256 or len(artifact_content_sha256) != 64 or not artifact_source_sha256 or len(artifact_source_sha256) != 64:
            is_valid = False
            reason = "invalid_hash"
        elif not anchor_quote or len(anchor_quote) > 4096 or len(anchor_prefix) > 32 or len(anchor_suffix) > 32:
            is_valid = False
            reason = "invalid_anchor"

        if is_valid:
            try:
                # Insert with v41 defaults.
                con.execute(
                    "INSERT INTO feedback_threads_v41 "
                    "(thread_id, owner_user_id, investigation_id, artifact_id, artifact_version, "
                    "artifact_content_sha256, artifact_source_sha256, normalization, "
                    "anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, "
                    "anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id, "
                    "create_request_sha256, entry_kind, highlight_color, resolution_event_id, "
                    "branch_investigation_id, branch_start_event_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'comment', NULL, NULL, NULL, NULL, ?, ?)",
                    [
                        row_dict["thread_id"], row_dict["owner_user_id"],
                        row_dict["investigation_id"], row_dict["artifact_id"],
                        row_dict["artifact_version"], row_dict["artifact_content_sha256"],
                        row_dict["artifact_source_sha256"], row_dict["normalization"],
                        row_dict["anchor_node_id"], row_dict["anchor_node_text_sha256"],
                        row_dict["anchor_start_scalar"], row_dict["anchor_end_scalar"],
                        row_dict["anchor_quote"], row_dict["anchor_prefix"],
                        row_dict["anchor_suffix"], row_dict["state"],
                        row_dict["create_operation_id"], row_dict["create_request_sha256"],
                        row_dict.get("created_at", now), row_dict.get("updated_at", now),
                    ]
                )
            except Exception:
                # Constraint violation → quarantine.
                is_valid = False
                reason = "unknown_malformation"

        if not is_valid:
            _quarantine_thread(con, row_dict, reason, now)


def _quarantine_thread(con: LockedConnection, row_dict: dict, reason: str, now: datetime) -> None:
    """Quarantine a malformed feedback_threads row."""
    original_row_sha256 = _sha256(canonical_row_json(row_dict, _source_columns("feedback_threads_v41")))
    q_id = _q_id("feedback_threads", original_row_sha256)
    evidence = _evidence({"thread_id": row_dict.get("thread_id")}, reason)

    con.execute(
        "INSERT INTO feedback_threads_v41_quarantine "
        "(quarantine_id, original_thread_id, reason, original_row_sha256, evidence_json, quarantined_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (quarantine_id) DO NOTHING",
        [q_id, _bounded_text(row_dict.get("thread_id")), reason, original_row_sha256, evidence, now]
    )


def _copy_items(con: LockedConnection, now: datetime) -> None:
    """Copy feedback_items to v41 with validation and quarantine."""
    baseline_cols = ", ".join(_source_columns("feedback_items_v41"))
    rows = con.execute(f"SELECT {baseline_cols} FROM feedback_items").fetchall()
    col_names = _source_columns("feedback_items_v41")

    # Build set of active v41 thread IDs for parent validation.
    active_threads = set()
    for r in con.execute("SELECT thread_id FROM feedback_threads_v41").fetchall():
        active_threads.add(r[0])

    for row in rows:
        row_dict = dict(zip(col_names, row, strict=False))
        is_valid = True
        reason = "unknown_malformation"

        item_id = row_dict.get("item_id", "")
        thread_id = row_dict.get("thread_id", "")
        author_kind = row_dict.get("author_kind", "")
        body_markdown = row_dict.get("body_markdown", "")

        if not item_id or len(item_id) > 256:
            is_valid = False
            reason = "invalid_shape"
        elif thread_id not in active_threads:
            is_valid = False
            reason = "missing_parent"
        elif author_kind not in ("operator", "agent", "system"):
            is_valid = False
            reason = "invalid_author"
        elif len(body_markdown) > 32768 or len(body_markdown) < 1:
            is_valid = False
            reason = "invalid_body"

        if is_valid:
            try:
                con.execute(
                    "INSERT INTO feedback_items_v41 "
                    "(item_id, thread_id, sequence, author_kind, author_id, entry_kind, body_markdown, work_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'comment', ?, ?, ?)",
                    [
                        row_dict["item_id"], row_dict["thread_id"],
                        row_dict["sequence"], row_dict["author_kind"],
                        row_dict["author_id"], row_dict["body_markdown"],
                        row_dict.get("work_id"), row_dict.get("created_at", now),
                    ]
                )
            except Exception:
                is_valid = False
                reason = "unknown_malformation"

        if not is_valid:
            _quarantine_item(con, row_dict, reason, now)


def _quarantine_item(con: LockedConnection, row_dict: dict, reason: str, now: datetime) -> None:
    """Quarantine a malformed feedback_items row."""
    original_row_sha256 = _sha256(canonical_row_json(row_dict, _source_columns("feedback_items_v41")))
    q_id = _q_id("feedback_items", original_row_sha256)
    evidence = _evidence({"item_id": row_dict.get("item_id"), "thread_id": row_dict.get("thread_id")}, reason)

    con.execute(
        "INSERT INTO feedback_items_v41_quarantine "
        "(quarantine_id, original_item_id, original_thread_id, reason, original_row_sha256, evidence_json, quarantined_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (quarantine_id) DO NOTHING",
        [q_id, _bounded_text(row_dict.get("item_id")), _bounded_text(row_dict.get("thread_id")), reason, original_row_sha256, evidence, now]
    )


def _copy_work(con: LockedConnection, now: datetime) -> None:
    """Copy agent_work to v41 with validation and quarantine."""
    baseline_cols = ", ".join(_source_columns("agent_work_v41"))
    rows = con.execute(f"SELECT {baseline_cols} FROM agent_work").fetchall()
    col_names = _source_columns("agent_work_v41")

    active_threads = set()
    for r in con.execute("SELECT thread_id FROM feedback_threads_v41").fetchall():
        active_threads.add(r[0])

    for row in rows:
        row_dict = dict(zip(col_names, row, strict=False))
        is_valid = True
        reason = "unknown_malformation"

        work_id = row_dict.get("work_id", "")
        thread_id = row_dict.get("thread_id", "")
        state = row_dict.get("state", "")
        row_dict.get("context_sha256", "")

        if not work_id or len(work_id) > 256:
            is_valid = False
            reason = "invalid_shape"
        elif thread_id not in active_threads:
            is_valid = False
            reason = "invalid_correlation"
        elif row_dict.get("attempt_count", 0) > 2:
            is_valid = False
            reason = "attempt_count_exceeded"
        elif state not in ("queued", "leased", "submitted", "acknowledged", "working",
                          "replied", "declined", "approval_requested", "failed",
                          "lease_expired", "retryable_failure"):
            is_valid = False
            reason = "invalid_state"

        if is_valid:
            try:
                con.execute(
                    "INSERT INTO agent_work_v41 "
                    "(work_id, thread_id, logical_worker_id, state, context_sha256, "
                    "attempt_count, active_lease_id, lease_expires_at, not_before, "
                    "last_error_code, result_sha256, created_at, updated_at, terminal_at, "
                    "dispatch_id, work_kind) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'feedback_reply')",
                    [
                        row_dict["work_id"], row_dict["thread_id"],
                        row_dict["logical_worker_id"], row_dict["state"],
                        row_dict["context_sha256"], row_dict["attempt_count"],
                        row_dict.get("active_lease_id"), row_dict.get("lease_expires_at"),
                        row_dict["not_before"], row_dict.get("last_error_code"),
                        row_dict.get("result_sha256"), row_dict.get("created_at", now),
                        row_dict.get("updated_at", now), row_dict.get("terminal_at"),
                    ]
                )
            except Exception:
                is_valid = False
                reason = "unknown_malformation"

        if not is_valid:
            _quarantine_work(con, row_dict, reason, now)


def _quarantine_work(con: LockedConnection, row_dict: dict, reason: str, now: datetime) -> None:
    """Quarantine a malformed agent_work row."""
    original_row_sha256 = _sha256(canonical_row_json(row_dict, _source_columns("agent_work_v41")))
    q_id = _q_id("agent_work", original_row_sha256)
    evidence = _evidence({"work_id": row_dict.get("work_id"), "thread_id": row_dict.get("thread_id"),
                          "state": row_dict.get("state"), "attempt_count": row_dict.get("attempt_count")}, reason)

    con.execute(
        "INSERT INTO agent_work_v41_quarantine "
        "(quarantine_id, original_work_id, reason, original_row_sha256, evidence_json, quarantined_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (quarantine_id) DO NOTHING",
        [q_id, _bounded_text(row_dict.get("work_id")), reason, original_row_sha256, evidence, now]
    )


def _copy_attempts(con: LockedConnection, now: datetime) -> None:
    """Copy agent_work_attempts to v41 with validation and quarantine."""
    baseline_cols = ", ".join(_source_columns("agent_work_attempts_v41"))
    rows = con.execute(f"SELECT {baseline_cols} FROM agent_work_attempts").fetchall()
    col_names = _source_columns("agent_work_attempts_v41")

    active_work = set()
    for r in con.execute("SELECT work_id FROM agent_work_v41").fetchall():
        active_work.add(r[0])

    for row in rows:
        row_dict = dict(zip(col_names, row, strict=False))
        is_valid = True
        reason = "unknown_malformation"

        attempt_id = row_dict.get("attempt_id", "")
        work_id = row_dict.get("work_id", "")
        state = row_dict.get("state", "")
        attempt_no = row_dict.get("attempt_no", 0)

        if not attempt_id or len(attempt_id) > 256:
            is_valid = False
            reason = "invalid_shape"
        elif work_id not in active_work:
            is_valid = False
            reason = "invalid_correlation"
        elif state not in ("leased", "submitted", "acknowledged", "working", "completed",
                          "failed", "lease_expired", "retryable_failure"):
            is_valid = False
            reason = "invalid_state"
        elif attempt_no < 1:
            is_valid = False
            reason = "invalid_attempt_no"

        if is_valid:
            try:
                con.execute(
                    "INSERT INTO agent_work_attempts_v41 "
                    "(attempt_id, work_id, attempt_no, lease_id, bridge_credential_id, "
                    "bridge_instance_id, state, lease_expires_at, herdr_target_observed, "
                    "adapter_version, transport_receipt_sha256, result_from_state, "
                    "submitted_at, acknowledged_at, working_at, completed_at, created_at, "
                    "dispatch_id, work_kind, attempt_actual_cents) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'feedback_reply', 0)",
                    [
                        row_dict["attempt_id"], row_dict["work_id"],
                        row_dict["attempt_no"], row_dict["lease_id"],
                        row_dict["bridge_credential_id"], row_dict["bridge_instance_id"],
                        row_dict["state"], row_dict["lease_expires_at"],
                        row_dict.get("herdr_target_observed"), row_dict.get("adapter_version"),
                        row_dict.get("transport_receipt_sha256"), row_dict.get("result_from_state"),
                        row_dict.get("submitted_at"), row_dict.get("acknowledged_at"),
                        row_dict.get("working_at"), row_dict.get("completed_at"),
                        row_dict.get("created_at", now),
                    ]
                )
            except Exception:
                is_valid = False
                reason = "unknown_malformation"

        if not is_valid:
            _quarantine_attempt(con, row_dict, reason, now)


def _apply_dependency_cascade(con: LockedConnection, now: datetime) -> None:
    """Quarantine whole aggregates when any dependent legacy row is unsafe."""
    thread_cols = _source_columns("feedback_threads_v41")
    item_cols = _source_columns("feedback_items_v41")
    work_cols = _source_columns("agent_work_v41")
    attempt_cols = _source_columns("agent_work_attempts_v41")
    thread_rows = {row[0]: dict(zip(thread_cols, row, strict=True)) for row in con.execute(
        f"SELECT {', '.join(thread_cols)} FROM feedback_threads").fetchall()}
    item_rows = [dict(zip(item_cols, row, strict=True)) for row in con.execute(
        f"SELECT {', '.join(item_cols)} FROM feedback_items").fetchall()]
    work_rows = {row[0]: dict(zip(work_cols, row, strict=True)) for row in con.execute(
        f"SELECT {', '.join(work_cols)} FROM agent_work").fetchall()}
    attempt_rows = [dict(zip(attempt_cols, row, strict=True)) for row in con.execute(
        f"SELECT {', '.join(attempt_cols)} FROM agent_work_attempts").fetchall()]

    bad_threads: set[Any] = set()
    quarantined_item_threads = con.execute(
        "SELECT DISTINCT original_thread_id FROM feedback_items_v41_quarantine "
        "WHERE original_thread_id IS NOT NULL"
    ).fetchall()
    bad_threads.update(row[0] for row in quarantined_item_threads)
    for row in thread_rows.values():
        sequences = sorted(item["sequence"] for item in item_rows if item["thread_id"] == row["thread_id"])
        if sequences and sequences != list(range(1, len(sequences) + 1)):
            bad_threads.add(row["thread_id"])

    bad_works = {row[0] for row in con.execute(
        "SELECT original_work_id FROM agent_work_v41_quarantine WHERE original_work_id IS NOT NULL"
    ).fetchall()}
    bad_attempt_works = {row[0] for row in con.execute(
        "SELECT original_work_id FROM agent_work_attempts_v41_quarantine WHERE original_work_id IS NOT NULL"
    ).fetchall()}
    bad_works.update(bad_attempt_works)
    for work_id in bad_works:
        work = work_rows.get(work_id)
        if work is not None:
            bad_threads.add(work["thread_id"])

    for thread_id in bad_threads:
        thread = thread_rows.get(thread_id)
        if thread is None:
            continue
        _quarantine_thread(con, thread, "invalid_shape", now)
        related_work_ids = {work["work_id"] for work in work_rows.values() if work["thread_id"] == thread_id}
        for item in (item for item in item_rows if item["thread_id"] == thread_id):
            _quarantine_item(con, item, "invalid_shape", now)
        for work in (work for work in work_rows.values() if work["thread_id"] == thread_id):
            _quarantine_work(con, work, "invalid_correlation", now)
        for attempt in (attempt for attempt in attempt_rows if attempt["work_id"] in related_work_ids):
            _quarantine_attempt(con, attempt, "invalid_correlation", now)
        con.execute("DELETE FROM agent_work_attempts_v41 WHERE work_id IN (SELECT work_id FROM agent_work_v41 WHERE thread_id = ?)", [thread_id])
        con.execute("DELETE FROM agent_work_v41 WHERE thread_id = ?", [thread_id])
        con.execute("DELETE FROM feedback_items_v41 WHERE thread_id = ?", [thread_id])
        con.execute("DELETE FROM feedback_threads_v41 WHERE thread_id = ?", [thread_id])


def _quarantine_attempt(con: LockedConnection, row_dict: dict, reason: str, now: datetime) -> None:
    """Quarantine a malformed agent_work_attempts row."""
    original_row_sha256 = _sha256(canonical_row_json(row_dict, _source_columns("agent_work_attempts_v41")))
    q_id = _q_id("agent_work_attempts", original_row_sha256)
    evidence = _evidence({"attempt_id": row_dict.get("attempt_id"), "work_id": row_dict.get("work_id"),
                          "state": row_dict.get("state"), "attempt_no": row_dict.get("attempt_no")}, reason)

    con.execute(
        "INSERT INTO agent_work_attempts_v41_quarantine "
        "(quarantine_id, original_attempt_id, original_work_id, reason, original_row_sha256, evidence_json, quarantined_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (quarantine_id) DO NOTHING",
        [q_id, _bounded_text(row_dict.get("attempt_id")), _bounded_text(row_dict.get("work_id")), reason, original_row_sha256, evidence, now]
    )


def _phase_rename(con: LockedConnection, *, expected: str) -> None:
    """Rename v41 tables to active names (one transaction)."""
    with _phase_transaction(con):
        con.execute("DROP TABLE IF EXISTS agent_work_attempts CASCADE")
        con.execute("DROP TABLE IF EXISTS agent_work CASCADE")
        con.execute("DROP TABLE IF EXISTS feedback_items CASCADE")
        con.execute("DROP TABLE IF EXISTS feedback_threads CASCADE")
        for table in ("feedback_threads_v41", "feedback_items_v41", "agent_work_v41", "agent_work_attempts_v41"):
            con.execute(f"ALTER TABLE {table} RENAME TO {table.replace('_v41', '')}")
        _cas_phase(con, expected, "renamed")


def _phase_complete(con: LockedConnection, *, expected: str) -> None:
    """Compute active digests and complete the marker."""
    with _phase_transaction(con):
        active_schema_sha, active_rows_sha = _migration_digests(con, active=True)
        marker = con.execute(
            "SELECT temp_schema_sha256, temp_rows_sha256 FROM schema_migrations "
            "WHERE migration_id = ?", [MIGRATION_ID]
        ).fetchone()
        if marker is None or (active_schema_sha, active_rows_sha) != (marker[0], marker[1]):
            raise RuntimeError("migration_conflict: active digest differs from copied digest")
        _cas_phase(
            con, expected, "completed",
            active_schema_sha256=active_schema_sha,
            active_rows_sha256=active_rows_sha,
            completed_at=_now_utc(),
        )
