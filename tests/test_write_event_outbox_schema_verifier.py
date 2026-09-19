from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.verify_write_event_outbox_schema import verify


def test_verifier_accepts_fresh_schema(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    verify(db)


def test_verifier_accepts_sequence_start_after_nextval_reopen(tmp_path) -> None:
    """Live DuckDB rewrites sequence start_value after committed use + reopen.

    Observed on prod: after nextval (via DEFAULT) and reopen, duckdb_sequences()
    reports start_value == last_value+1 (START in sql also advances). Deploy
    schema verify must not treat that as contract breakage so
    infrastructure/ansible/playbooks/deploy.yml can pass this step again.
    """
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    sha = "a" * 64
    with connect_write(db, purpose="test/outbox-seq-advance") as con:
        con.execute(
            "INSERT INTO write_event_outbox("
            "event_id, operation_id, investigation_id, aggregate_kind, "
            "aggregate_id, event_json, event_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["evt-1", "op-1", "inv-1", "kind", "agg-1", "{}", sha],
        )
        start_same_conn = con.execute(
            "SELECT start_value FROM duckdb_sequences() "
            "WHERE sequence_name='write_event_outbox_sequence'"
        ).fetchone()[0]
    # Same connection may still report the original start_value column.
    assert start_same_conn == 1

    with connect_write(db, purpose="test/outbox-seq-reopen") as con:
        start_after_reopen, increment_by, sql = con.execute(
            "SELECT start_value, increment_by, sql FROM duckdb_sequences() "
            "WHERE sequence_name='write_event_outbox_sequence'"
        ).fetchone()
    assert start_after_reopen == 2  # DuckDB quirk: START becomes last_value+1
    assert increment_by == 1
    assert "START 2" in sql

    verify(db)  # must pass despite advanced start_value


def test_verifier_rejects_missing_sequence(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="test/drop-outbox-seq") as con:
        # Drop table first so sequence has no dependents, then sequence.
        con.execute("DROP TABLE write_event_outbox")
        con.execute("DROP SEQUENCE write_event_outbox_sequence")
    with pytest.raises(RuntimeError, match="sequences:"):
        verify(db)


def test_verifier_rejects_wrong_increment(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="test/wrong-outbox-incr") as con:
        con.execute("DROP TABLE write_event_outbox")
        con.execute("DROP SEQUENCE write_event_outbox_sequence")
        con.execute(
            "CREATE SEQUENCE write_event_outbox_sequence START 1 INCREMENT 2"
        )
        con.execute(
            "CREATE TABLE write_event_outbox ("
            "outbox_sequence BIGINT PRIMARY KEY "
            "DEFAULT nextval('write_event_outbox_sequence'), "
            "event_id VARCHAR NOT NULL, "
            "operation_id VARCHAR NOT NULL, "
            "investigation_id VARCHAR NOT NULL, "
            "aggregate_kind VARCHAR NOT NULL, "
            "aggregate_id VARCHAR NOT NULL, "
            "event_json VARCHAR NOT NULL, "
            "event_sha256 VARCHAR NOT NULL, "
            "state VARCHAR NOT NULL DEFAULT 'pending', "
            "attempt_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "delivered_at TIMESTAMP, "
            "CHECK (attempt_count >= 0), "
            "CHECK (state IN ('pending', 'delivered')), "
            "UNIQUE (event_id), "
            "UNIQUE (operation_id)"
            ")"
        )
        con.execute(
            "CREATE INDEX idx_write_event_outbox_pending ON "
            "write_event_outbox(investigation_id, state, outbox_sequence)"
        )
    with pytest.raises(RuntimeError, match="sequences:"):
        verify(db)


def test_verifier_rejects_missing_outbox_table(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="test/drop-outbox-table") as con:
        con.execute("DROP TABLE write_event_outbox")
    with pytest.raises(RuntimeError, match="columns:"):
        verify(db)
