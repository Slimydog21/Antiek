"""Strict post-derived-asset schema for immutable twin-note merge bridges."""

from __future__ import annotations

from runtime.db_lock import LockedConnection

BRIDGE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS twin_note_merge_bridges (
    bridge_id TEXT PRIMARY KEY CHECK (regexp_full_match(bridge_id,'tmb_[0-9a-f]{32}')),
    owner_user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(request_sha256,'[0-9a-f]{64}') AND request_sha256=sha256(request_json)
    ),
    source_projection_id TEXT NOT NULL,
    twin_source_kind TEXT NOT NULL CHECK (twin_source_kind IN ('revision','composition')),
    twin_source_id TEXT NOT NULL CHECK (regexp_full_match(twin_source_id,'tn[rc]-[0-9a-f]{32}')),
    manifest_json TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(manifest_sha256,'[0-9a-f]{64}') AND manifest_sha256=sha256(manifest_json)
    ),
    appendix_html_bytes BLOB NOT NULL,
    appendix_html_byte_count BIGINT NOT NULL CHECK (
        appendix_html_byte_count=octet_length(appendix_html_bytes) AND appendix_html_byte_count>0
    ),
    appendix_html_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(appendix_html_sha256,'[0-9a-f]{64}')
        AND appendix_html_sha256=sha256(appendix_html_bytes)
    ),
    projection_id TEXT NOT NULL UNIQUE CHECK (regexp_full_match(projection_id,'hproj-[0-9a-f]{64}')),
    object_locator TEXT NOT NULL,
    object_state TEXT NOT NULL DEFAULT 'pending' CHECK (object_state IN ('pending','published')),
    publication_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (publication_attempt_count>=0),
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_user_id,idempotency_key),
    UNIQUE (owner_user_id,request_sha256),
    CHECK ((object_state='pending' AND published_at IS NULL)
        OR (object_state='published' AND published_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_twin_note_merge_bridges_owner_source
    ON twin_note_merge_bridges(owner_user_id,twin_source_kind,twin_source_id);
CREATE INDEX IF NOT EXISTS idx_twin_note_merge_bridges_pending
    ON twin_note_merge_bridges(object_state,created_at);

CREATE TABLE IF NOT EXISTS twin_note_merge_bridge_members (
    bridge_id TEXT NOT NULL,
    member_ordinal INTEGER NOT NULL CHECK (member_ordinal>=0),
    revision_id TEXT NOT NULL CHECK (regexp_full_match(revision_id,'tnr-[0-9a-f]{32}')),
    note_ordinal INTEGER NOT NULL CHECK (note_ordinal>=0),
    revision_body_sha256 TEXT NOT NULL CHECK (regexp_full_match(revision_body_sha256,'[0-9a-f]{64}')),
    revision_html_sha256 TEXT NOT NULL CHECK (regexp_full_match(revision_html_sha256,'[0-9a-f]{64}')),
    canonical_note_sha256 TEXT NOT NULL CHECK (regexp_full_match(canonical_note_sha256,'[0-9a-f]{64}')),
    PRIMARY KEY (bridge_id,member_ordinal),
    UNIQUE (bridge_id,revision_id,note_ordinal)
);
"""

TABLES = ("twin_note_merge_bridges", "twin_note_merge_bridge_members")

EXPECTED_DESCRIBE = {
    "twin_note_merge_bridges": [
        ("bridge_id", "VARCHAR", "NO", "PRI", None),
        ("owner_user_id", "VARCHAR", "NO", "UNI", None),
        ("idempotency_key", "VARCHAR", "NO", "UNI", None),
        ("request_json", "VARCHAR", "NO", None, None),
        ("request_sha256", "VARCHAR", "NO", "UNI", None),
        ("source_projection_id", "VARCHAR", "NO", None, None),
        ("twin_source_kind", "VARCHAR", "NO", None, None),
        ("twin_source_id", "VARCHAR", "NO", None, None),
        ("manifest_json", "VARCHAR", "NO", None, None),
        ("manifest_sha256", "VARCHAR", "NO", None, None),
        ("appendix_html_bytes", "BLOB", "NO", None, None),
        ("appendix_html_byte_count", "BIGINT", "NO", None, None),
        ("appendix_html_sha256", "VARCHAR", "NO", None, None),
        ("projection_id", "VARCHAR", "NO", "UNI", None),
        ("object_locator", "VARCHAR", "NO", None, None),
        ("object_state", "VARCHAR", "NO", None, "'pending'"),
        ("publication_attempt_count", "INTEGER", "NO", None, "0"),
        ("published_at", "TIMESTAMP", "YES", None, None),
        ("created_at", "TIMESTAMP", "NO", None, "CURRENT_TIMESTAMP"),
    ],
    "twin_note_merge_bridge_members": [
        ("bridge_id", "VARCHAR", "NO", "PRI", None),
        ("member_ordinal", "INTEGER", "NO", "PRI", None),
        ("revision_id", "VARCHAR", "NO", "UNI", None),
        ("note_ordinal", "INTEGER", "NO", "UNI", None),
        ("revision_body_sha256", "VARCHAR", "NO", None, None),
        ("revision_html_sha256", "VARCHAR", "NO", None, None),
        ("canonical_note_sha256", "VARCHAR", "NO", None, None),
    ],
}

EXPECTED_KEYS = {
    "twin_note_merge_bridges": {
        ("PRIMARY KEY", ("bridge_id",), "PRIMARY KEY(bridge_id)"),
        ("UNIQUE", ("projection_id",), "UNIQUE(projection_id)"),
        ("UNIQUE", ("owner_user_id", "idempotency_key"), "UNIQUE(owner_user_id, idempotency_key)"),
        ("UNIQUE", ("owner_user_id", "request_sha256"), "UNIQUE(owner_user_id, request_sha256)"),
    },
    "twin_note_merge_bridge_members": {
        ("PRIMARY KEY", ("bridge_id", "member_ordinal"), "PRIMARY KEY(bridge_id, member_ordinal)"),
        ("UNIQUE", ("bridge_id", "revision_id", "note_ordinal"), "UNIQUE(bridge_id, revision_id, note_ordinal)"),
    },
}

EXPECTED_CHECK_COUNTS = {
    "twin_note_merge_bridges": 11,
    "twin_note_merge_bridge_members": 6,
}


def install(con: LockedConnection) -> None:
    """Install bridge receipts, repairing only malformed empty partial state."""
    existing = _existing(con)
    if existing and not shape_is_valid(con):
        if any(int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]) for table in existing):
            raise RuntimeError("populated partial twin-note merge bridge schema requires explicit recovery")
        for table in reversed(TABLES):
            if table in existing:
                con.execute(f"DROP TABLE {table}")
    con.execute(BRIDGE_SCHEMA_SQL)
    if not shape_is_valid(con):
        raise RuntimeError("twin-note merge bridge schema shape is invalid")


def sentinel_is_present(con: object) -> bool:
    return shape_is_valid(con)


def _existing(con: object) -> set[str]:
    placeholders = ",".join("?" for _ in TABLES)
    return {str(row[0]) for row in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' "
        f"AND table_name IN ({placeholders})", list(TABLES)).fetchall()}


def shape_is_valid(con: object) -> bool:
    if _existing(con) != set(TABLES):
        return False
    for table in TABLES:
        if [tuple(row[:5]) for row in con.execute(f"DESCRIBE main.{table}").fetchall()] != EXPECTED_DESCRIBE[table]:
            return False
        rows = con.execute(
            "SELECT constraint_type,constraint_column_names,constraint_text,"
            "referenced_table,referenced_column_names FROM duckdb_constraints() "
            "WHERE schema_name='main' AND table_name=? AND constraint_type IN "
            "('PRIMARY KEY','UNIQUE','FOREIGN KEY')", [table]).fetchall()
        keys = {(row[0], tuple(row[1]),
                 f"REFERENCES:{row[3]}({','.join(row[4])})" if row[0] == "FOREIGN KEY" else row[2])
                for row in rows}
        if keys != EXPECTED_KEYS[table]:
            return False
        checks = con.execute(
            "SELECT constraint_text FROM duckdb_constraints() WHERE schema_name='main' "
            "AND table_name=? AND constraint_type='CHECK'", [table]).fetchall()
        if len(checks) != EXPECTED_CHECK_COUNTS[table]:
            return False
    indexes = {str(row[0]) for row in con.execute(
        "SELECT index_name FROM duckdb_indexes() WHERE schema_name='main' "
        "AND table_name IN ('twin_note_merge_bridges','twin_note_merge_bridge_members')"
    ).fetchall()}
    return indexes == {
        "idx_twin_note_merge_bridges_owner_source", "idx_twin_note_merge_bridges_pending"
    }


__all__ = ["BRIDGE_SCHEMA_SQL", "install", "sentinel_is_present", "shape_is_valid"]
