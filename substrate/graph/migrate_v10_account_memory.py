"""Account-memory S2a schema migration.

DuckDB cannot widen ``nodes.node_type``'s CHECK in place, while ``edges``
foreign-keys ``nodes``. This repeats the staged, FK-free copy dance proven by
``migrate_v9_insight_question`` and also adds nullable ``edges.owner_user_id``.
The migration is explicit/operator-run: importing or initializing the graph does
not execute it against an existing database.
"""

from __future__ import annotations

import contextlib
import re

from runtime.db_lock import LockedConnection, connect_write

NODE_TYPES_AFTER = (
    "entity",
    "organization",
    "person",
    "property",
    "metric",
    "mechanism",
    "claim",
    "method",
    "constraint",
    "insight",
    "question",
    "memory",
)


def _node_type_check_clause() -> str:
    return "node_type IN (" + ", ".join(f"'{value}'" for value in NODE_TYPES_AFTER) + ")"


_NODES_REBUILD_SQL = f"""
CREATE TABLE nodes_mig (
    node_id          TEXT PRIMARY KEY,
    canonical_label  TEXT NOT NULL,
    node_type        TEXT NOT NULL CHECK ({_node_type_check_clause()}),
    embedding        FLOAT[],
    graph_scope      TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached    INTEGER NOT NULL DEFAULT 0,
    metadata         TEXT,
    owner_user_id    TEXT
)
"""

_EDGES_REBUILD_SQL = """
CREATE TABLE edges (
    edge_id                TEXT PRIMARY KEY,
    source_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    relation               TEXT NOT NULL,
    chunk_id               TEXT REFERENCES chunks(chunk_id),
    source_document_id     TEXT REFERENCES documents(document_id),
    source_tier            INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    extraction_confidence  FLOAT NOT NULL
        CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    extracted_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from             TIMESTAMP NOT NULL DEFAULT '1970-01-01',
    valid_until            TIMESTAMP,
    superseded_by          TEXT REFERENCES edges(edge_id),
    graph_scope            TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    investigation_id       TEXT,
    metadata               TEXT,
    owner_user_id          TEXT
)
"""

_EDGE_COLS = (
    "edge_id",
    "source_node_id",
    "target_node_id",
    "relation",
    "chunk_id",
    "source_document_id",
    "source_tier",
    "extraction_confidence",
    "extracted_at",
    "valid_from",
    "valid_until",
    "superseded_by",
    "graph_scope",
    "investigation_id",
    "metadata",
    "owner_user_id",
)

_NODE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_scope ON nodes(graph_scope)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(canonical_label)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_degree ON nodes(degree_cached)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_owner ON nodes(owner_user_id)",
)

_EDGE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_scope ON edges(graph_scope)",
    "CREATE INDEX IF NOT EXISTS idx_edges_valid ON edges(valid_from, valid_until)",
    "CREATE INDEX IF NOT EXISTS idx_edges_chunk ON edges(chunk_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(extraction_confidence)",
    "CREATE INDEX IF NOT EXISTS idx_edges_tier ON edges(source_tier)",
    "CREATE INDEX IF NOT EXISTS idx_edges_extracted ON edges(extracted_at)",
    "CREATE INDEX IF NOT EXISTS idx_edges_owner ON edges(owner_user_id)",
)


def _table_exists(con: LockedConnection, table: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = ? LIMIT 1",
            [table],
        ).fetchone()
        is not None
    )


def _normalize_sql(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _normalized_node_type_check(node_types: tuple[str, ...]) -> str:
    values = ",".join(f"'{value}'" for value in node_types)
    return f"check((node_typein({values})))"


def _nodes_have_memory(con: LockedConnection) -> bool:
    checks = [
        _normalize_sql(str(row[0]))
        for row in con.execute(
            "SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name = 'nodes' AND constraint_type = 'CHECK'"
        ).fetchall()
        if row and row[0] is not None and "node_type" in str(row[0]).lower()
    ]
    if len(checks) != 1:
        raise RuntimeError("nodes must have exactly one recognizable node_type CHECK")
    expected = _normalized_node_type_check(NODE_TYPES_AFTER)
    before = _normalized_node_type_check(NODE_TYPES_AFTER[:-1])
    if checks[0] == expected:
        return True
    if checks[0] == before:
        return False
    raise RuntimeError("nodes node_type CHECK is not a recognized v9/v10 shape")


def _edges_have_owner(con: LockedConnection) -> bool:
    rows = con.execute(
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = 'edges' "
        "AND column_name = 'owner_user_id'"
    ).fetchall()
    if not rows:
        return False
    if rows == [("VARCHAR", "YES")]:
        return True
    raise RuntimeError("edges.owner_user_id must be nullable TEXT")


def _owner_index_exists(con: LockedConnection) -> bool:
    rows = con.execute(
        "SELECT table_name, expressions, is_unique FROM duckdb_indexes() "
        "WHERE schema_name='main' AND index_name='idx_edges_owner'"
    ).fetchall()
    if not rows:
        return False
    if len(rows) != 1:
        raise RuntimeError("idx_edges_owner is ambiguous")
    table_name, expressions, is_unique = rows[0]
    normalized = re.sub(r'[\s"\']', "", str(expressions)).lower()
    if table_name != "edges" or normalized != "[owner_user_id]" or bool(is_unique):
        raise RuntimeError("idx_edges_owner must index only edges.owner_user_id")
    return True


def _existing_graph_index_sql(con: LockedConnection) -> list[str]:
    return [
        str(row[0])
        for row in con.execute(
            "SELECT sql FROM duckdb_indexes() WHERE schema_name='main' "
            "AND table_name IN ('nodes','edges') AND sql IS NOT NULL "
            "ORDER BY index_name"
        ).fetchall()
    ]


def migrate(con: LockedConnection) -> bool:
    """Apply the explicit account-memory migration atomically.

    Returns ``True`` when either schema delta was applied and ``False`` when the
    database already has both. ``con`` must not already be in a transaction.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "migrate_v10_account_memory requires a LockedConnection; use "
            "runtime.db_lock.connect_write"
        )
    if con.in_explicit_transaction:
        raise RuntimeError("migrate_v10_account_memory manages its own transaction")
    nodes_exists = _table_exists(con, "nodes")
    edges_exists = _table_exists(con, "edges")
    if not nodes_exists and not edges_exists:
        raise RuntimeError("initialize the graph schema before migrate_v10_account_memory")
    if not nodes_exists or not edges_exists:
        raise RuntimeError("account-memory migration requires both nodes and edges")

    needs_nodes_rebuild = not _nodes_have_memory(con)
    needs_edge_owner = not _edges_have_owner(con)
    needs_owner_index = not _owner_index_exists(con)
    if not needs_nodes_rebuild and not needs_edge_owner and not needs_owner_index:
        return False

    nodes_before = int(con.execute("SELECT count(*) FROM nodes").fetchone()[0])
    edges_before = int(con.execute("SELECT count(*) FROM edges").fetchone()[0])
    preserved_index_sql = (
        _existing_graph_index_sql(con) if needs_nodes_rebuild else []
    )
    con.execute("BEGIN")
    try:
        if needs_edge_owner:
            con.execute("ALTER TABLE edges ADD COLUMN owner_user_id TEXT")

        if needs_nodes_rebuild:
            con.execute(_NODES_REBUILD_SQL)
            con.execute("INSERT INTO nodes_mig BY NAME SELECT * FROM nodes")
            con.execute("CREATE TABLE edges_stage AS SELECT * FROM edges")
            con.execute("DROP TABLE edges")
            con.execute("DROP TABLE nodes")
            con.execute("ALTER TABLE nodes_mig RENAME TO nodes")
            con.execute(_EDGES_REBUILD_SQL)
            columns = ", ".join(_EDGE_COLS)
            staged = ", ".join(
                "NULL" if column == "superseded_by" else column
                for column in _EDGE_COLS
            )
            con.execute(
                f"INSERT INTO edges ({columns}) SELECT {staged} FROM edges_stage"
            )
            con.execute(
                "UPDATE edges SET superseded_by = staged.superseded_by "
                "FROM edges_stage staged WHERE edges.edge_id = staged.edge_id "
                "AND staged.superseded_by IS NOT NULL"
            )
            con.execute("DROP TABLE edges_stage")
            for ddl in preserved_index_sql:
                con.execute(ddl)
            for ddl in (*_NODE_INDEXES, *_EDGE_INDEXES):
                con.execute(ddl)
        else:
            con.execute(_EDGE_INDEXES[-1])

        nodes_after = int(con.execute("SELECT count(*) FROM nodes").fetchone()[0])
        edges_after = int(con.execute("SELECT count(*) FROM edges").fetchone()[0])
        if (nodes_after, edges_after) != (nodes_before, edges_before):
            raise RuntimeError(
                "migrate_v10_account_memory row-count mismatch: "
                f"nodes {nodes_before}->{nodes_after}, edges {edges_before}->{edges_after}"
            )
        if (
            not _nodes_have_memory(con)
            or not _edges_have_owner(con)
            or not _owner_index_exists(con)
        ):
            raise RuntimeError("migrate_v10_account_memory postcondition failed")
        con.execute("COMMIT")
    except Exception:
        with contextlib.suppress(Exception):
            con.execute("ROLLBACK")
        raise
    return True


def migrate_at_path(db_path: str) -> bool:
    """Acquire the serialized writer and apply :func:`migrate`."""
    con = connect_write(db_path, purpose="migrate_v10_account_memory")
    try:
        return migrate(con)
    finally:
        con.close()


if __name__ == "__main__":  # pragma: no cover - operator CLI
    import argparse

    parser = argparse.ArgumentParser(
        description="Add account-memory node typing and edge ownership"
    )
    parser.add_argument("--db-path", required=True)
    arguments = parser.parse_args()
    changed = migrate_at_path(arguments.db_path)
    print("migrated" if changed else "no-op (already migrated or uninitialized)")
