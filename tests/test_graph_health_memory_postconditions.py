"""SPR-11 T4: the three account-memory v10 postconditions on /health.

A fresh ``init_database_at_path`` schema already carries the ``memory`` node type
and ``edges.owner_user_id``, but ``idx_edges_owner`` is created ONLY by
``migrate_v10_account_memory``. So the honest reading of a fresh database is
two True and one False, and the False is a pending migration rather than an
outage — which is why the fields ride next to, not inside, ``duckdb_ready``.
The original spec bar asked for all three True against a fresh schema; that is
a falsehood and is deliberately not asserted here.
"""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api.app import create_app  # noqa: E402
from substrate.graph.health import probe_duckdb_health  # noqa: E402
from substrate.graph.migrate_v10_account_memory import migrate_at_path  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402

_MEMORY_KEYS = {
    "memory_node_type_ready",
    "memory_edges_owner_ready",
    "memory_owner_index_ready",
}


def test_fresh_schema_reports_pending_owner_index_not_an_outage(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))

    health = probe_duckdb_health(str(db_path))

    assert health.memory_node_type_ready is True
    assert health.memory_edges_owner_ready is True
    # idx_edges_owner is the migration's, never schema.py's.
    assert health.memory_owner_index_ready is False
    # Pending migration, not outage: the DB is still ready.
    assert health.ready is True
    assert health.status == "ok"


def test_after_migration_all_three_postconditions_hold(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    assert probe_duckdb_health(str(db_path)).memory_owner_index_ready is False

    # The migration is explicit and operator-run; the probe never calls it.
    assert migrate_at_path(str(db_path)) is True

    health = probe_duckdb_health(str(db_path))
    assert health.memory_node_type_ready is True
    assert health.memory_edges_owner_ready is True
    assert health.memory_owner_index_ready is True
    assert health.ready is True


def test_missing_or_unreadable_file_reports_all_three_false(tmp_path):
    missing = probe_duckdb_health(str(tmp_path / "missing.duckdb"))
    assert (
        missing.memory_node_type_ready,
        missing.memory_edges_owner_ready,
        missing.memory_owner_index_ready,
    ) == (False, False, False)

    corrupt = tmp_path / "corrupt.duckdb"
    corrupt.write_bytes(b"not a duckdb database")
    unreadable = probe_duckdb_health(str(corrupt))
    assert (
        unreadable.memory_node_type_ready,
        unreadable.memory_edges_owner_ready,
        unreadable.memory_owner_index_ready,
    ) == (False, False, False)


def test_health_route_exposes_exactly_the_three_memory_keys(tmp_path, monkeypatch):
    """Mirror of the production bar: the keys containing "memory" are exactly
    these three, read as JSON, with the first two True on a fresh schema."""
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    body = TestClient(app).get("/health").json()

    memory_fields = {key: value for key, value in body.items() if "memory" in key}
    assert set(memory_fields) == _MEMORY_KEYS, sorted(_MEMORY_KEYS - set(memory_fields))
    assert memory_fields["memory_node_type_ready"] is True
    assert memory_fields["memory_edges_owner_ready"] is True
    assert memory_fields["memory_owner_index_ready"] is False
    assert body["duckdb_ready"] is True


def test_health_route_reads_the_startup_snapshot_not_a_fresh_probe(tmp_path, monkeypatch):
    """The fields must ride app.state.duckdb_health: a migration applied after
    startup is NOT visible until restart, which is the proof that /health did
    not open a second connection per request."""
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    assert client.get("/health").json()["memory_owner_index_ready"] is False

    assert migrate_at_path(str(db_path)) is True
    assert probe_duckdb_health(str(db_path)).memory_owner_index_ready is True

    assert client.get("/health").json()["memory_owner_index_ready"] is False
