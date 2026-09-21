"""SPR-11 Task 4 — v10 account-memory schema postconditions on /health.

Three read-only booleans ride the existing startup-cached DuckDB probe. The
tests here settle three separate questions, and each one is written so that it
fails if the thing it guards is removed:

1. against a database the v10 migration has actually been applied to, all
   three report ``True``;
2. against the schema ``init_database_at_path`` ships today -- which carries
   the ``memory`` node type and ``edges.owner_user_id`` but *not*
   ``idx_edges_owner``, since only the migration creates that index -- the
   owner-index field reports ``False`` while the other two stay ``True``.
   A probe that hard-coded ``True``, or that collapsed all three into one
   answer, fails this test;
3. ``/health`` surfaces all three, and serving a request opens **no** DuckDB
   connection: the values come from ``app.state.duckdb_health``, cached once
   at app construction. A per-request opener would be a writer-lock conflict
   and a single-writer violation, so the connection count is asserted, not
   assumed.
"""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api.app import create_app  # noqa: E402
from substrate.graph import health as health_module  # noqa: E402
from substrate.graph.health import probe_duckdb_health  # noqa: E402
from substrate.graph.migrate_v10_account_memory import migrate_at_path  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402

_MEMORY_FIELDS = (
    "duckdb_memory_nodes_ready",
    "duckdb_memory_edges_owner_ready",
    "duckdb_memory_owner_index_ready",
)


def test_migrated_schema_reports_all_three_postconditions_true(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    # The explicit, operator-run migration is what creates idx_edges_owner.
    # Applying it here is what makes this the "v10 applied" state rather than
    # the "v10 partially present" state exercised by the next test.
    assert migrate_at_path(str(db_path)) is True

    health = probe_duckdb_health(str(db_path))

    assert health.ready is True
    assert health.memory_nodes_ready is True
    assert health.memory_edges_owner_ready is True
    assert health.memory_owner_index_ready is True
    # Idempotent: a second migrate is a no-op and the postconditions hold.
    assert migrate_at_path(str(db_path)) is False
    assert probe_duckdb_health(str(db_path)).memory_owner_index_ready is True


def test_schema_without_owner_index_reports_only_that_field_false(tmp_path):
    db_path = tmp_path / "graph.duckdb"
    # No migrate_at_path call: substrate/graph/schema.py creates the 'memory'
    # node type and edges.owner_user_id directly, but idx_edges_owner exists
    # only in migrate_v10_account_memory. This is therefore a real, reachable
    # partial-v10 database, not a hand-mangled fixture.
    init_database_at_path(str(db_path))

    index_rows = _owner_index_rows(str(db_path))
    assert index_rows == [], f"fixture premise broken: idx_edges_owner exists ({index_rows})"

    health = probe_duckdb_health(str(db_path))

    assert health.memory_owner_index_ready is False
    assert health.memory_nodes_ready is True
    assert health.memory_edges_owner_ready is True
    # The missing index is reported, not escalated: overall DB health is
    # untouched by the v10 postconditions.
    assert health.ready is True
    assert health.status == "ok"


def test_missing_database_reports_all_three_false_without_raising(tmp_path):
    health = probe_duckdb_health(str(tmp_path / "absent.duckdb"))

    assert health.status == "missing"
    assert health.memory_nodes_ready is False
    assert health.memory_edges_owner_ready is False
    assert health.memory_owner_index_ready is False


def test_health_route_serves_postconditions_without_opening_a_connection(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    assert migrate_at_path(str(db_path)) is True
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    opens: list[str] = []
    real_connect_read = health_module.connect_read

    def counting_connect_read(path: str):
        opens.append(path)
        return real_connect_read(path)

    monkeypatch.setattr(health_module, "connect_read", counting_connect_read)

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    opens_after_startup = len(opens)
    assert opens_after_startup == 1, "startup must probe exactly once"

    client = TestClient(app)
    first = client.get("/health").json()
    second = client.get("/health").json()

    # The load-bearing assertion: two requests, still one open. If the probe
    # were moved into the request handler this is the line that reds.
    assert len(opens) == opens_after_startup, (
        f"/health opened {len(opens) - opens_after_startup} extra DuckDB "
        "connection(s); it must read the startup-cached snapshot"
    )

    for body in (first, second):
        assert sorted(k for k in body if "memory" in k) == sorted(_MEMORY_FIELDS)
        assert body["duckdb_memory_nodes_ready"] is True
        assert body["duckdb_memory_edges_owner_ready"] is True
        assert body["duckdb_memory_owner_index_ready"] is True


def _owner_index_rows(db_path: str) -> list[tuple]:
    con = health_module.connect_read(db_path)
    try:
        return list(
            con.execute(
                "SELECT index_name FROM duckdb_indexes() "
                "WHERE schema_name='main' AND index_name='idx_edges_owner'"
            ).fetchall()
        )
    finally:
        con.close()
