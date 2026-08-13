from __future__ import annotations

from pathlib import Path

import pytest

from runtime.db_lock import LockedConnection, connect_write
from substrate.graph.migrate_v10_account_memory import migrate
from substrate.graph.schema import init_database_at_path

_LEGACY_SQL = """
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    source_tier INTEGER NOT NULL,
    document_type TEXT NOT NULL
);
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    canonical_label TEXT NOT NULL,
    node_type TEXT NOT NULL CHECK (node_type IN (
        'entity', 'organization', 'person', 'property', 'metric', 'mechanism',
        'claim', 'method', 'constraint', 'insight', 'question'
    )),
    embedding FLOAT[],
    graph_scope TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached INTEGER NOT NULL DEFAULT 0,
    metadata TEXT,
    owner_user_id TEXT
);
CREATE TABLE edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    relation TEXT NOT NULL,
    chunk_id TEXT REFERENCES chunks(chunk_id),
    source_document_id TEXT REFERENCES documents(document_id),
    source_tier INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    extraction_confidence FLOAT NOT NULL CHECK (
        extraction_confidence >= 0 AND extraction_confidence <= 1
    ),
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from TIMESTAMP NOT NULL DEFAULT '1970-01-01',
    valid_until TIMESTAMP,
    superseded_by TEXT REFERENCES edges(edge_id),
    graph_scope TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')),
    investigation_id TEXT,
    metadata TEXT
);
"""


def _columns(con: LockedConnection, table: str) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name=?",
            [table],
        ).fetchall()
    }


def _node_check(con: LockedConnection) -> str:
    return " ".join(
        str(row[0])
        for row in con.execute(
            "SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name='nodes' AND constraint_type='CHECK'"
        ).fetchall()
    )


def test_migrate_v10_upgrades_fresh_legacy_db_and_is_idempotent(
    tmp_path: Path,
) -> None:
    con = connect_write(str(tmp_path / "legacy.duckdb"), purpose="legacy-v10-test")
    try:
        con.execute(_LEGACY_SQL)
        assert migrate(con) is True
        assert "'memory'" in _node_check(con)
        assert "owner_user_id" in _columns(con, "edges")
        assert migrate(con) is False
    finally:
        con.close()


def test_migrate_v10_preserves_rows_self_links_and_owner_values(
    tmp_path: Path,
) -> None:
    con = connect_write(str(tmp_path / "populated.duckdb"), purpose="legacy-v10-data")
    try:
        con.execute(_LEGACY_SQL)
        con.execute(
            "INSERT INTO nodes (node_id,canonical_label,node_type,graph_scope,owner_user_id) "
            "VALUES ('n1','one','entity','depth','user-a'),"
            "('n2','two','claim','depth','user-a')"
        )
        con.execute(
            "INSERT INTO edges (edge_id,source_node_id,target_node_id,relation,"
            "source_tier,extraction_confidence,graph_scope) "
            "VALUES ('e2','n1','n2','newer',1,1.0,'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id,source_node_id,target_node_id,relation,"
            "source_tier,extraction_confidence,superseded_by,graph_scope) "
            "VALUES ('e1','n1','n2','older',1,0.8,'e2','depth')"
        )

        assert migrate(con) is True
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (2,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (2,)
        assert con.execute(
            "SELECT superseded_by,owner_user_id FROM edges WHERE edge_id='e1'"
        ).fetchone() == ("e2", None)
        con.execute(
            "INSERT INTO nodes (node_id,canonical_label,node_type,graph_scope,owner_user_id) "
            "VALUES ('m1','remembered','memory','depth','user-a')"
        )
    finally:
        con.close()


def test_current_fresh_schema_already_has_v10_shape(tmp_path: Path) -> None:
    db_path = str(tmp_path / "fresh-current.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="fresh-v10-shape")
    try:
        assert "'memory'" in _node_check(con)
        assert "owner_user_id" in _columns(con, "edges")
        assert migrate(con) is True
        assert migrate(con) is False
    finally:
        con.close()


def test_migrate_v10_rejects_malformed_owner_column(tmp_path: Path) -> None:
    con = connect_write(str(tmp_path / "bad-owner.duckdb"), purpose="bad-owner-v10")
    try:
        con.execute(_LEGACY_SQL)
        con.execute("ALTER TABLE edges ADD COLUMN owner_user_id INTEGER")
        with pytest.raises(RuntimeError, match="nullable TEXT"):
            migrate(con)
        assert "'memory'" not in _node_check(con)
    finally:
        con.close()


def test_migrate_v10_rejects_wrong_owner_index(tmp_path: Path) -> None:
    db_path = str(tmp_path / "bad-index.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="bad-index-v10")
    try:
        con.execute("CREATE INDEX idx_edges_owner ON edges(relation)")
        with pytest.raises(RuntimeError, match="only edges.owner_user_id"):
            migrate(con)
    finally:
        con.close()


def test_migrate_v10_rejects_deceptive_node_check(tmp_path: Path) -> None:
    deceptive_sql = _LEGACY_SQL.replace(
        "'insight', 'question'\n    )),",
        "'insight', 'question', 'memory'\n    ) AND node_type <> 'memory'),",
    )
    con = connect_write(
        str(tmp_path / "bad-check.duckdb"), purpose="bad-check-v10"
    )
    try:
        con.execute(deceptive_sql)
        with pytest.raises(RuntimeError, match="not a recognized v9/v10 shape"):
            migrate(con)
    finally:
        con.close()
