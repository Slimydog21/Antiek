from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph import schema as graph_schema
from substrate.graph.schema import init_database_at_path
from substrate.graph.twin_note_merge_bridge_schema import shape_is_valid


def test_fresh_install_and_reopen(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="bridge-schema-proof") as con:
        assert shape_is_valid(con)
    graph_schema._INITIALIZED_PATHS.discard(db)
    init_database_at_path(db)
    with connect_write(db, purpose="bridge-schema-reopen") as con:
        assert shape_is_valid(con)


def test_empty_partial_schema_is_repaired(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="bridge-schema-empty-partial") as con:
        con.execute("DROP TABLE twin_note_merge_bridge_members")
    graph_schema._INITIALIZED_PATHS.discard(db)
    init_database_at_path(db)
    with connect_write(db, purpose="bridge-schema-empty-partial-proof") as con:
        assert shape_is_valid(con)


def test_populated_partial_schema_fails_closed(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with connect_write(db, purpose="bridge-schema-populated-partial") as con:
        payload = b"x"
        con.execute(
            "INSERT INTO twin_note_merge_bridges (bridge_id,owner_user_id,idempotency_key,"
            "request_json,request_sha256,source_projection_id,twin_source_kind,twin_source_id,"
            "manifest_json,manifest_sha256,appendix_html_bytes,appendix_html_byte_count,appendix_html_sha256,"
            "projection_id,object_locator) VALUES "
            "('tmb_00000000000000000000000000000000','owner','key','{}',sha256('{}'),'source',"
            "'revision','tnr-00000000000000000000000000000000','{}',sha256('{}'),?,?,?,"
            "'hproj-0000000000000000000000000000000000000000000000000000000000000000',"
            "'bridge/x.html')",
            [payload, len(payload), hashlib.sha256(payload).hexdigest()],
        )
        con.execute("DROP TABLE twin_note_merge_bridge_members")
    graph_schema._INITIALIZED_PATHS.discard(db)
    with pytest.raises(RuntimeError, match="populated partial twin-note merge bridge schema"):
        init_database_at_path(db)
