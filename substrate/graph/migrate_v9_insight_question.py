"""DRW SPR-01 — promote ``insight`` + ``question`` to graph node types.

Predecessor: the V9 ``write_log`` block in ``schema.py`` (after the
V7/V8 Read/Write-workflow blocks). This is the first *procedural*
migration in the graph layer.

Why a module and not another idempotent SQL constant
----------------------------------------------------
The V1..V7 schema blocks are pure ``CREATE ... IF NOT EXISTS`` /
``ALTER ... ADD COLUMN IF NOT EXISTS`` strings, run unconditionally by
``init_database``. Adding ``insight`` + ``question`` to the
``nodes.node_type`` CHECK cannot be expressed that way: **DuckDB 1.5.2
supports neither ``ALTER TABLE ... ADD/DROP CONSTRAINT`` for CHECK nor
an in-place CHECK edit** (verified — both raise
``NotImplementedException``). The only mechanism is to rebuild the
table with the wider CHECK and copy the rows.

Why the rebuild is a staged dance, not a simple create-copy-rename
------------------------------------------------------------------
``edges.source_node_id`` / ``edges.target_node_id`` are FOREIGN KEYs to
``nodes(node_id)``, and DuckDB **refuses to drop or rename a table that
is an FK target** while the referrer exists (``DependencyException``).
So a temp ``nodes_mig`` cannot be renamed to ``nodes`` while ``edges``
(or a temp ``edges_mig`` that references it) is present. The working
sequence — validated empirically against DuckDB 1.5.2:

  1. build ``nodes_mig`` with the wider CHECK, copy rows;
  2. stage ``edges`` into an **FK-free** ``edges_stage`` (``CREATE TABLE
     AS`` drops constraints) so nothing references the old ``nodes``;
  3. drop ``edges`` then ``nodes`` (now unreferenced);
  4. rename ``nodes_mig`` -> ``nodes`` (now unreferenced — succeeds);
  5. recreate ``edges`` fresh with every FK + the ``superseded_by``
     self-FK pointing at the correctly-named ``nodes``;
  6. restore edge rows; ``superseded_by`` is inserted NULL then patched
     by a follow-up UPDATE so the self-FK never sees a forward
     reference mid-insert;
  7. recreate the ``nodes`` + ``edges`` indexes (dropped with their
     tables).

The whole sequence runs inside one transaction. DuckDB DDL is
transactional (MVCC catalog), so a failure mid-rebuild rolls the graph
back to its pre-migration state — verified.

Idempotency
-----------
``_already_has_insight_question`` reads the live CHECK text from
``duckdb_constraints()``. If both literals are present the migration is
a no-op and returns ``False``. So: fresh DBs (whose V1 constant already
carries the two types) skip the rebuild; a second run skips it; only a
pre-existing prod DB with the narrow CHECK is rebuilt, exactly once.

Data-safety guarantees
----------------------
Row counts for ``nodes`` and ``edges`` are asserted equal before/after
(inside the transaction; a mismatch raises and rolls back). Column
order, every CHECK, every FK, and ``superseded_by`` self-references are
preserved (asserted by ``tests/test_graph_insight_question.py``). Back
up ``~/.antiek/research_graph.duckdb`` before running against prod
regardless — the migration does not snapshot for you.
"""

from __future__ import annotations

import contextlib
import os
import sys

try:
    from ...runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]


# The node-type list AFTER this migration. Must stay in lock-step with
# the V1 CHECK in schema.py and substrate/schemas/events.NodeType. The
# two new members are the only delta from the legacy 9-type taxonomy.
NODE_TYPES_AFTER = (
    "entity", "organization", "person", "property",
    "metric", "mechanism", "claim", "method", "constraint",
    "insight", "question",
)
_NEW_NODE_TYPES = ("insight", "question")


def _node_type_check_clause() -> str:
    quoted = ", ".join(f"'{t}'" for t in NODE_TYPES_AFTER)
    return f"node_type IN ({quoted})"


# Rebuilt-table DDL. These MUST mirror the ``nodes`` / ``edges`` blocks
# in schema.py exactly except for the widened node_type CHECK. The drift
# test in tests/test_graph_insight_question.py rebuilds a fresh DB and
# asserts column parity, so a future column added to schema.py without a
# matching edit here is caught.
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
    source_tier            INTEGER NOT NULL
        CHECK (source_tier BETWEEN 1 AND 5),
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
    metadata               TEXT
)
"""

# Explicit column list keeps the superseded_by self-FK from seeing a
# forward reference during the bulk insert: it lands NULL, then a follow-up
# UPDATE restores it.
_EDGE_COLS = (
    "edge_id", "source_node_id", "target_node_id", "relation", "chunk_id",
    "source_document_id", "source_tier", "extraction_confidence",
    "extracted_at", "valid_from", "valid_until", "superseded_by",
    "graph_scope", "investigation_id", "metadata",
)

_EDGE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_edges_source  ON edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target  ON edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_scope   ON edges(graph_scope)",
    "CREATE INDEX IF NOT EXISTS idx_edges_valid   ON edges(valid_from, valid_until)",
    "CREATE INDEX IF NOT EXISTS idx_edges_chunk   ON edges(chunk_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(extraction_confidence)",
    "CREATE INDEX IF NOT EXISTS idx_edges_tier    ON edges(source_tier)",
)

_NODE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_nodes_type    ON nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_scope   ON nodes(graph_scope)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_label   ON nodes(canonical_label)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_degree  ON nodes(degree_cached)",
)


def _nodes_check_text(con: LockedConnection) -> str:
    """The live CHECK clause on ``nodes`` (empty string if the table or
    constraint is absent). Read-only introspection."""
    try:
        rows = con.execute(
            "SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name = 'nodes' AND constraint_type = 'CHECK'"
        ).fetchall()
    except Exception:
        return ""
    # node_type and graph_scope both have CHECKs; concatenate so the probe
    # is order-independent.
    return " ".join(r[0] for r in rows if r and r[0])


def _already_has_insight_question(con: LockedConnection) -> bool:
    text = _nodes_check_text(con)
    return all(f"'{t}'" in text for t in _NEW_NODE_TYPES)


def migrate(con: LockedConnection) -> bool:
    """Apply the insight/question node-type migration on ``con``.

    Returns ``True`` if a rebuild was performed, ``False`` if it was a
    no-op (already migrated, or the ``nodes`` table does not exist yet —
    in which case V1 already carries the wider CHECK).

    ``con`` MUST be a write-locked ``LockedConnection`` and MUST NOT
    already be inside an explicit transaction — this function manages its
    own BEGIN/COMMIT so the rebuild is atomic.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "migrate_v9_insight_question requires a LockedConnection "
            f"(got {type(con).__name__}); use runtime.db_lock.connect_write."
        )

    # No nodes table at all → nothing to rebuild; V1 will have created it
    # with the wider CHECK on a fresh DB.
    exists = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = 'nodes' LIMIT 1"
    ).fetchone()
    if not exists:
        return False

    if _already_has_insight_question(con):
        return False

    n_nodes_before = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
    n_edges_before = con.execute("SELECT count(*) FROM edges").fetchone()[0]

    col_csv = ", ".join(_EDGE_COLS)
    select_with_null_sup = ", ".join(
        "NULL" if c == "superseded_by" else c for c in _EDGE_COLS
    )

    con.execute("BEGIN")
    try:
        # 1. new nodes table (wider CHECK), copy rows.
        con.execute(_NODES_REBUILD_SQL)
        con.execute("INSERT INTO nodes_mig BY NAME SELECT * FROM nodes")
        # 2. FK-free staging copy of edges (CREATE AS drops constraints).
        con.execute("CREATE TABLE edges_stage AS SELECT * FROM edges")
        # 3. drop the FK web that pins the old nodes table.
        con.execute("DROP TABLE edges")
        con.execute("DROP TABLE nodes")
        # 4. rename — now nothing references nodes_mig.
        con.execute("ALTER TABLE nodes_mig RENAME TO nodes")
        # 5. recreate edges with the full FK set + self-FK.
        con.execute(_EDGES_REBUILD_SQL)
        # 6. restore rows; superseded_by lands NULL then is patched so the
        #    self-FK never sees a forward reference during the insert.
        con.execute(
            f"INSERT INTO edges ({col_csv}) "
            f"SELECT {select_with_null_sup} FROM edges_stage"
        )
        con.execute(
            "UPDATE edges SET superseded_by = s.superseded_by "
            "FROM edges_stage s "
            "WHERE edges.edge_id = s.edge_id AND s.superseded_by IS NOT NULL"
        )
        con.execute("DROP TABLE edges_stage")
        # 7. recreate indexes (dropped with their tables).
        for ddl in (*_NODE_INDEXES, *_EDGE_INDEXES):
            con.execute(ddl)

        # Data-safety gate: row counts must be conserved or we roll back.
        n_nodes_after = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
        n_edges_after = con.execute("SELECT count(*) FROM edges").fetchone()[0]
        if (n_nodes_after, n_edges_after) != (n_nodes_before, n_edges_before):
            raise RuntimeError(
                "migrate_v9_insight_question row-count mismatch — refusing to "
                f"commit. nodes {n_nodes_before}->{n_nodes_after}, "
                f"edges {n_edges_before}->{n_edges_after}."
            )
        con.execute("COMMIT")
    except Exception:
        with contextlib.suppress(Exception):
            con.execute("ROLLBACK")
        raise
    return True


def migrate_at_path(db_path: str) -> bool:
    """Acquire a write lock on ``db_path`` and run :func:`migrate`.
    Convenience for tests and the standalone CLI."""
    con = connect_write(db_path, purpose="migrate_v9_insight_question")
    try:
        return migrate(con)
    finally:
        con.close()


if __name__ == "__main__":  # pragma: no cover — operator CLI
    import argparse

    p = argparse.ArgumentParser(
        description="DRW SPR-01 — add insight/question node types (V8)."
    )
    p.add_argument("--db-path", required=True, help="Path to the DuckDB graph file")
    args = p.parse_args()
    changed = migrate_at_path(args.db_path)
    print("migrated (rebuilt nodes table)" if changed else "no-op (already migrated)")
