from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.verify_event_consumer_schema import verify


def test_verifier_rejects_semantic_chain_and_receipt_corruption(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="test/seed_consumer_corruption") as con:
        con.execute(
            "INSERT INTO event_consumer_events VALUES "
            "('consumer', 1, 'inv', 0, 'evt', 'note.emerged', ?, "
            "'succeeded', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ["1" * 64, "2" * 64],
        )
        con.execute(
            "INSERT INTO event_consumer_frontiers "
            "(consumer_name, consumer_version, investigation_id, next_ordinal, "
            "chain_sha256) VALUES ('consumer', 1, 'inv', 1, ?)",
            ["2" * 64],
        )

    with pytest.raises(RuntimeError, match="chain mismatch|receipt/ledger mismatch"):
        verify(db)


def test_verifier_accepts_empty_exact_schema(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    verify(db)
