"""Spec-derived exact digest vectors for the SPR-01 migration.

Pins canonical_row_json, schema_digest, and row_digest to golden SHA-256
values computed independently from the accepted sprint-01 algorithm text:
"canonical_row_json(row,columns) builds a JSON object with exactly the named
columns in sorted key order, NFC-normalized strings, RFC3339 UTC timestamps,
JSON null for SQL NULL, ensure_ascii=true, and compact separators.
schema_digest(tables) is sha256(canonical_json([{\"table\":name,\"ddl\":
normalized_create_sql} for name in FEEDBACK_V41_TABLE_ORDER])).
row_digest(tables) is sha256(canonical_json([{\"table\":name,\"rows\":
[canonical_row_json(row,columns) ... sorted by primary key]} ...]))."

Any drift in the implementation fails these literal vectors.
"""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import duckdb

from substrate.feedback.migrations import (
    _CANONICAL_PRIMARY_KEYS,
    V41_TABLE_ORDER,
    _actual_schema_ddls,
    _get_v41_ddl,
    canonical_row_json,
    row_digest,
    schema_digest,
)

NINE_TABLES = (
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

VECTOR_ROW = {
    "thread_id": "thread\u0301",  # NFD; must NFC-normalize inside the digest
    "state": "open",
    "sequence": 3,
    "active": True,
    "work_id": None,
    "created_at": datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
}
VECTOR_COLUMNS = ("thread_id", "state", "sequence", "active", "work_id", "created_at")

CANONICAL_ROW_VECTOR_SHA = "941595bbe082885bbc54d4091719a677c6f9c3f1013c8f45f40aaf5f3c65d7b6"
SCHEMA_DIGEST_VECTOR_SHA = "31a37d4e17a9c8bc18c98b6e8826736b4214ec8c4ce9f56aaa5aa515221489cb"
ROW_DIGEST_VECTOR_SHA = "f04c65609bff7a049e7352f5e4414c00afada55213f9c94b39504503cb821a1e"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_table_order_matches_spec() -> None:
    assert V41_TABLE_ORDER == NINE_TABLES


def test_provenance_uses_composite_primary_key() -> None:
    assert _CANONICAL_PRIMARY_KEYS["feedback_provenance"] == ("thread_id", "ref_index")


def test_canonical_row_json_golden_vector() -> None:
    blob = canonical_row_json(VECTOR_ROW, VECTOR_COLUMNS)
    assert _sha(blob) == CANONICAL_ROW_VECTOR_SHA
    # Exact canonical text: sorted keys, compact separators, ensure_ascii
    # escapes, RFC3339 UTC timestamp, JSON null, NFC-stable id.
    expected = (
        '{"active":true,"created_at":"2026-08-29T06:30:00Z","sequence":3,'
        '"state":"open","thread_id":"thread' + chr(92) + 'u0301","work_id":null}'
    )
    assert blob.decode() == expected


def test_canonical_row_json_normalizes_nfd_to_nfc() -> None:
    nfd = "cafe\u0301"
    nfc = unicodedata.normalize("NFC", nfd)
    out_nfd = canonical_row_json({"v": nfd}, ("v",)).decode()
    out_nfc = canonical_row_json({"v": nfc}, ("v",)).decode()
    assert out_nfd == out_nfc, "NFD input must digest identically to its NFC form"


def test_schema_digest_golden_vector() -> None:
    ddls = {name: f"CREATE TABLE IF NOT EXISTS {name} (x INTEGER);" for name in NINE_TABLES}
    assert schema_digest(ddls) == SCHEMA_DIGEST_VECTOR_SHA


def test_row_digest_golden_vector() -> None:
    rows_by_table = {name: [] for name in NINE_TABLES}
    columns_by_table = {name: ("id",) for name in NINE_TABLES}
    rows_by_table["feedback_threads_v41"] = [
        {"thread_id": "z", "state": None},
        {"thread_id": "a", "state": "open"},
    ]
    columns_by_table["feedback_threads_v41"] = ("thread_id", "state")
    rows_by_table["feedback_provenance"] = [
        {"thread_id": "b", "ref_index": 1, "v": "y"},
        {"thread_id": "a", "ref_index": 2, "v": "x"},
        {"thread_id": "a", "ref_index": 1, "v": "w"},
    ]
    columns_by_table["feedback_provenance"] = ("thread_id", "ref_index", "v")
    assert row_digest(rows_by_table, columns_by_table) == ROW_DIGEST_VECTOR_SHA


# --- DDL normalization pins -------------------------------------------------
# _actual_schema_ddls digests DuckDB's stored catalog SQL (see its docstring).
# These pins make rendering drift — e.g. from a DuckDB upgrade — fail loudly
# instead of silently changing schema digests and breaking resume idempotency.

ACTUAL_PROVENANCE_DDL_PREFIX = (
    "CREATE TABLE feedback_provenance(thread_id VARCHAR, owner_user_id VARCHAR "
    "NOT NULL, ref_index INTEGER, node_id VARCHAR NOT NULL"
)
ACTUAL_SCHEMA_DIGEST_VECTOR_SHA = "c1bbb94773d5c9c54dec5c813967b5bc7f46ab0a2394e177be09f5c02ba507af"


def _v41_catalog() -> Any:
    con = duckdb.connect(":memory:")
    con.execute(_get_v41_ddl())
    return con


def test_actual_schema_ddls_deterministic_and_golden() -> None:
    first = _actual_schema_ddls(_v41_catalog(), active=False)
    second = _actual_schema_ddls(_v41_catalog(), active=False)
    assert first == second, "catalog rendering must be deterministic across connections"

    assert set(first) == set(NINE_TABLES)
    provenance = first["feedback_provenance"]
    assert provenance.startswith(ACTUAL_PROVENANCE_DDL_PREFIX)
    assert "IF NOT EXISTS" not in provenance, "DuckDB drops it from stored SQL"
    assert "CHECK(" in provenance, "constraints are hoisted into the stored rendering"
    assert schema_digest(first) == ACTUAL_SCHEMA_DIGEST_VECTOR_SHA


def test_schema_digest_stable_across_connections() -> None:
    a = _actual_schema_ddls(_v41_catalog(), active=False)
    b = _actual_schema_ddls(_v41_catalog(), active=False)
    assert schema_digest(a) == schema_digest(b)
