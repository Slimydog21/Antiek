"""Fail closed unless the crash-recoverable write outbox contract is exact."""

from __future__ import annotations

import argparse

from runtime.db_lock import connect_write

EXPECTED_COLUMNS = [
    ("outbox_sequence", "BIGINT", "NO", "nextval('write_event_outbox_sequence')"),
    ("event_id", "VARCHAR", "NO", None),
    ("operation_id", "VARCHAR", "NO", None),
    ("investigation_id", "VARCHAR", "NO", None),
    ("aggregate_kind", "VARCHAR", "NO", None),
    ("aggregate_id", "VARCHAR", "NO", None),
    ("event_json", "VARCHAR", "NO", None),
    ("event_sha256", "VARCHAR", "NO", None),
    ("state", "VARCHAR", "NO", "'pending'"),
    ("attempt_count", "INTEGER", "NO", "0"),
    ("created_at", "TIMESTAMP", "NO", "CURRENT_TIMESTAMP"),
    ("delivered_at", "TIMESTAMP", "YES", None),
]
EXPECTED_CONSTRAINTS = [
    ("CHECK", "CHECK((attempt_count >= 0))"),
    ("CHECK", "CHECK((state IN ('pending', 'delivered')))"),
    *(("NOT NULL", "NOT NULL"),) * 11,
    ("PRIMARY KEY", "PRIMARY KEY(outbox_sequence)"),
    ("UNIQUE", "UNIQUE(event_id)"),
    ("UNIQUE", "UNIQUE(operation_id)"),
]
EXPECTED_INDEX = [
    (
        "idx_write_event_outbox_pending",
        "[investigation_id, state, outbox_sequence]",
        "CREATE INDEX idx_write_event_outbox_pending ON "
        "write_event_outbox(investigation_id, state, outbox_sequence);",
    )
]
EXPECTED_SEQUENCE = [("write_event_outbox_sequence", 1, 1)]


def verify(db_path: str) -> None:
    with connect_write(db_path, purpose="deploy/schema_verify", timeout_s=30) as con:
        columns = con.execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema='main' "
            "AND table_name='write_event_outbox' ORDER BY ordinal_position"
        ).fetchall()
        constraints = con.execute(
            "SELECT constraint_type, constraint_text FROM duckdb_constraints() "
            "WHERE table_name='write_event_outbox' "
            "ORDER BY constraint_type, constraint_text"
        ).fetchall()
        index = con.execute(
            "SELECT index_name, expressions, sql FROM duckdb_indexes() "
            "WHERE table_name='write_event_outbox' ORDER BY index_name"
        ).fetchall()
        sequence = con.execute(
            "SELECT sequence_name, start_value, increment_by "
            "FROM duckdb_sequences() "
            "WHERE sequence_name='write_event_outbox_sequence'"
        ).fetchall()

    mismatches = []
    for name, actual, expected in (
        ("columns", columns, EXPECTED_COLUMNS),
        ("constraints", constraints, EXPECTED_CONSTRAINTS),
        ("indexes", index, EXPECTED_INDEX),
        ("sequences", sequence, EXPECTED_SEQUENCE),
    ):
        if actual != expected:
            mismatches.append(f"{name}: expected {expected!r}, got {actual!r}")
    if mismatches:
        raise RuntimeError("write outbox schema contract mismatch; " + "; ".join(mismatches))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()
    verify(args.db_path)
    print("write outbox schema contract verified")


if __name__ == "__main__":
    main()
