from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.twin_note_taker.compression import DurableTwinNoteCompression
from substrate.twin_note_taker.serving import TwinNoteIntegrityError, TwinNoteServingService, TwinNoteUnavailable


def _canon(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def _sha(v): return hashlib.sha256(v.encode() if isinstance(v, str) else v).hexdigest()


@pytest.fixture
def served(tmp_path):
    db = str(tmp_path / "graph.duckdb"); init_database_at_path(db)
    for wid, iid, text in (("w-a", "inv-a", "Alpha"), ("w-b", "inv-b", "Beta")):
        sources = [f"evt-{iid}"]; sj = _canon(sources)
        request = _canon({"investigation_id": iid, "source_event_ids": sources}); raw = _canon({"notes": [{"text": text, "confidence": "high", "source_event_ids": sources}]})
        with connect_write(db, purpose="test/c48-seed") as con:
            con.execute("INSERT INTO note_taker_windows (window_id,consumer_version,investigation_id,threshold,ordinal,first_event_id,last_event_id,source_event_ids_json,source_digest,request_json,request_sha256,provider_idempotency_key,state,raw_result,raw_result_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [wid, 2, iid, 5, 0, sources[0], sources[0], sj, _sha(sj), request, _sha(request), wid, "completed", raw, _sha(raw)])
    events = tmp_path / "events"; events.mkdir()
    compressor = DurableTwinNoteCompression(lambda *_: True, db_path=db, publication_root=tmp_path / "published", events_dir=str(events))
    a = compressor.compress(account_id="__operator__", asset_id="asset", window_ids=("w-a",))
    b = compressor.compress(account_id="__operator__", asset_id="asset", window_ids=("w-b",), expected_predecessor=a.revision_id)
    return db, TwinNoteServingService(db_path=db), a, b


def _snapshot(db: str) -> tuple[tuple[str, tuple], ...]:
    """Logical snapshot: stable across DuckDB checkpoint/reopen details."""
    tables = ("twin_note_revisions", "twin_note_revision_members", "twin_note_publication_effects",
              "twin_note_compositions", "twin_note_composition_members", "note_taker_windows")
    with connect_read(db) as con:
        return tuple((table, tuple(con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall())) for table in tables)


def _v22_snapshot(db: str) -> tuple:
    with connect_read(db) as con:
        tables = tuple(con.execute("SELECT table_name,sql FROM duckdb_tables() WHERE schema_name='main' AND table_name LIKE 'twin_note_composition%' ORDER BY table_name").fetchall())
        indexes = tuple(con.execute("SELECT index_name,sql FROM duckdb_indexes() WHERE schema_name='main' AND table_name LIKE 'twin_note_composition%' ORDER BY index_name").fetchall())
        data = []
        for table, _ in tables:
            data.append((table, tuple(con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall())))
        return tables, indexes, tuple(data)


def _corrupt_revision_parent(db: str, revision_id: str, sql: str, params: list) -> None:
    """Work around DuckDB rejecting any update of an FK-referenced parent row."""
    with connect_write(db, purpose="test/c48-corrupt-revision-parent") as con:
        members = con.execute("SELECT * FROM twin_note_revision_members WHERE revision_id=?", [revision_id]).fetchall()
        effects = con.execute("SELECT * FROM twin_note_publication_effects WHERE revision_id=?", [revision_id]).fetchall()
        con.execute("DELETE FROM twin_note_revision_members WHERE revision_id=?", [revision_id])
        con.execute("DELETE FROM twin_note_publication_effects WHERE revision_id=?", [revision_id])
        con.execute(sql, params)
        for row in members: con.execute("INSERT INTO twin_note_revision_members VALUES (?,?,?,?,?,?,?,?)", list(row))
        for row in effects: con.execute("INSERT INTO twin_note_publication_effects VALUES (?,?,?,?,?,?,?,?)", list(row))


def test_owner_history_exact_bytes_and_ordered_identity(served):
    _, service, a, b = served
    assert service.assets("__operator__")[0]["current_revision"]["revision_id"] == b.revision_id
    assert [r.revision_id for r in service.history("__operator__", "asset")] == [b.revision_id, a.revision_id]
    assert service.revision("__operator__", a.revision_id).html_bytes == a.html_bytes
    ab = service.compose("__operator__", [a.revision_id, b.revision_id]); ba = service.compose("__operator__", [b.revision_id, a.revision_id])
    assert ab["composition_id"] != ba["composition_id"]
    assert [m["member_ordinal"] for m in ab["members"]] == [0, 1]
    assert service.composition("__operator__", ab["composition_id"]).index(b"Alpha") < service.composition("__operator__", ab["composition_id"]).index(b"Beta")


def test_foreign_and_missing_are_indistinguishable(served):
    _, service, a, _ = served
    for account, revision in (("foreign", a.revision_id), ("__operator__", "tnr-" + "0" * 32)):
        with pytest.raises(TwinNoteUnavailable): service.revision(account, revision)


def test_revision_member_authority_drift_conflict(served):
    db, service, _, _ = served
    with connect_write(db, purpose="test/c48-corrupt") as con:
        con.execute("UPDATE note_taker_windows SET raw_result='corrupt' WHERE window_id='w-a'")
    with pytest.raises(TwinNoteIntegrityError): service.history("__operator__", "asset")


def test_composition_full_row_and_member_reverified(served):
    db, service, a, b = served; result = service.compose("__operator__", [a.revision_id, b.revision_id])
    with connect_write(db, purpose="test/c48-corrupt") as con:
        con.execute("UPDATE twin_note_composition_members SET body_sha256='bad' WHERE member_ordinal=0")
    with pytest.raises(TwinNoteIntegrityError): service.composition("__operator__", result["composition_id"])


@pytest.mark.parametrize("corruption", [
    "broken_predecessor", "cross_owner_predecessor", "multiple_roots", "body", "html", "count", "member", "effect", "effect_state",
])
def test_revision_corruption_matrix_fails_closed(served, corruption):
    db, service, a, b = served
    placeholder = "tnr-" + "f" * 32
    if corruption in {"broken_predecessor", "cross_owner_predecessor"}:
        with connect_write(db, purpose="test/c48-placeholder-predecessor") as con:
            con.execute("INSERT INTO twin_note_revisions SELECT ?,?,?,?,compressor_version,renderer_version,?,body_json,body_sha256,html_bytes,html_sha256,?,note_count,source_event_count,created_at FROM twin_note_revisions WHERE revision_id=?",
                        [placeholder, "foreign" if corruption == "cross_owner_predecessor" else "__operator__",
                         "other-asset", None,
                         "f" * 64, "other/path.html", a.revision_id])
    statements = {
        "broken_predecessor": ("UPDATE twin_note_revisions SET supersedes_revision_id=? WHERE revision_id=?", [placeholder, b.revision_id]),
        "cross_owner_predecessor": ("UPDATE twin_note_revisions SET supersedes_revision_id=? WHERE revision_id=?", [placeholder, b.revision_id]),
        "multiple_roots": ("UPDATE twin_note_revisions SET supersedes_revision_id=NULL WHERE revision_id=?", [b.revision_id]),
        "body": ("UPDATE twin_note_revisions SET body_json='{}' WHERE revision_id=?", [b.revision_id]),
        "html": ("UPDATE twin_note_revisions SET html_bytes='wrong' WHERE revision_id=?", [b.revision_id]),
        "count": ("UPDATE twin_note_revisions SET note_count=note_count+1 WHERE revision_id=?", [b.revision_id]),
        "member": ("UPDATE twin_note_revision_members SET source_digest='bad' WHERE revision_id=?", [a.revision_id]),
        "effect": ("UPDATE twin_note_publication_effects SET expected_sha256='bad' WHERE revision_id=?", [a.revision_id]),
        "effect_state": ("UPDATE twin_note_publication_effects SET state='pending' WHERE revision_id=?", [a.revision_id]),
    }
    sql, params = statements[corruption]
    if corruption in {"broken_predecessor", "cross_owner_predecessor", "multiple_roots", "body", "html", "count"}:
        _corrupt_revision_parent(db, b.revision_id, sql, params)
    else:
        with connect_write(db, purpose="test/c48-corruption-matrix") as con: con.execute(sql, params)
    with pytest.raises(TwinNoteIntegrityError):
        service.history("__operator__", "asset")


def test_fork_is_unrepresentable_under_v21_unique_successor_constraint(served):
    db, service, a, _ = served
    with connect_write(db, purpose="test/c48-fork-constraint") as con, pytest.raises(duckdb.ConstraintException):
        con.execute("INSERT INTO twin_note_revisions SELECT 'tnr-ffffffffffffffffffffffffffffffff',account_id,asset_id,?,compressor_version,renderer_version,'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',body_json,body_sha256,html_bytes,html_sha256,'fork/path.html',note_count,source_event_count,created_at FROM twin_note_revisions WHERE revision_id=?", [a.revision_id, a.revision_id])
    assert service.history("__operator__", "asset")


@pytest.mark.parametrize("column,value", [
    ("ordered_members_sha256", "bad"), ("html_bytes", b"bad"),
    ("html_sha256", "bad"), ("member_count", 3), ("created_at", "2001-01-01"),
])
def test_composition_row_corruption_matrix(served, column, value):
    db, service, a, b = served
    made = service.compose("__operator__", [a.revision_id, b.revision_id])
    with connect_write(db, purpose="test/c48-composition-row-corruption") as con:
        members = con.execute("SELECT * FROM twin_note_composition_members WHERE composition_id=? ORDER BY member_ordinal", [made["composition_id"]]).fetchall()
        con.execute("DELETE FROM twin_note_composition_members WHERE composition_id=?", [made["composition_id"]])
        con.execute(f"UPDATE twin_note_compositions SET {column}=? WHERE composition_id=?", [value, made["composition_id"]])
        for row in members: con.execute("INSERT INTO twin_note_composition_members VALUES (?,?,?,?,?,?)", list(row))
    with pytest.raises(TwinNoteIntegrityError): service.composition("__operator__", made["composition_id"])


@pytest.mark.parametrize("column,value", [
    ("revision_id", "tnr-" + "f" * 32), ("asset_id", "other"),
    ("body_sha256", "bad"), ("html_sha256", "bad"),
])
def test_composition_member_corruption_matrix(served, column, value):
    db, service, a, b = served
    made = service.compose("__operator__", [a.revision_id, b.revision_id])
    with connect_write(db, purpose="test/c48-composition-member-corruption") as con:
        con.execute(f"UPDATE twin_note_composition_members SET {column}=? WHERE composition_id=? AND member_ordinal=0", [value, made["composition_id"]])
    with pytest.raises((TwinNoteIntegrityError, TwinNoteUnavailable)):
        service.composition("__operator__", made["composition_id"])


def test_gets_are_pure_and_database_unchanged(served, monkeypatch):
    db, service, a, b = served
    made = service.compose("__operator__", [a.revision_id, b.revision_id])
    before = _snapshot(db)
    def forbidden(*args, **kwargs): raise AssertionError("GET crossed a write/filesystem/provider/model seam")
    monkeypatch.setattr("substrate.twin_note_taker.serving.connect_write", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert service.assets("__operator__")
    assert service.history("__operator__", "asset")
    assert service.revision("__operator__", a.revision_id).html_bytes == a.html_bytes
    assert service.composition("__operator__", made["composition_id"])
    assert _snapshot(db) == before


def test_retry_reopen_and_concurrent_identical_composition(served):
    db, service, a, b = served
    ids = [a.revision_id, b.revision_id]
    first = service.compose("__operator__", ids)
    first_bytes = service.composition("__operator__", first["composition_id"])
    reopened = TwinNoteServingService(db_path=db)
    assert reopened.compose("__operator__", ids) == first
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: TwinNoteServingService(db_path=db).compose("__operator__", ids), range(8)))
    assert results == [first] * 8
    assert reopened.composition("__operator__", first["composition_id"]) == first_bytes
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_compositions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM twin_note_composition_members").fetchone() == (2,)


def test_v22_empty_repairs_but_populated_malformed_does_not(tmp_path):
    db = str(tmp_path / "schema.duckdb"); init_database_at_path(db)
    with connect_write(db, purpose="test/c48-schema") as con:
        con.execute("DROP TABLE twin_note_composition_members"); con.execute("DROP TABLE twin_note_compositions"); con.execute("CREATE TABLE twin_note_compositions (composition_id TEXT)")
    from substrate.graph.schema import _INITIALIZED_PATHS
    _INITIALIZED_PATHS.discard(db)
    init_database_at_path(db)
    with connect_read(db) as con: assert con.execute("SELECT COUNT(*) FROM twin_note_compositions").fetchone() == (0,)
    with connect_write(db, purpose="test/c48-schema") as con:
        con.execute("DROP TABLE twin_note_composition_members"); con.execute("DROP TABLE twin_note_compositions"); con.execute("CREATE TABLE twin_note_compositions (composition_id TEXT)"); con.execute("INSERT INTO twin_note_compositions VALUES ('occupied')")
    _INITIALIZED_PATHS.discard(db)
    before = _v22_snapshot(db)
    with pytest.raises(RuntimeError): init_database_at_path(db)
    assert _v22_snapshot(db) == before


def test_v22_valid_populated_schema_reopens(served):
    db, service, a, b = served
    made = service.compose("__operator__", [a.revision_id, b.revision_id])
    from substrate.graph.schema import _INITIALIZED_PATHS
    _INITIALIZED_PATHS.discard(db)
    init_database_at_path(db)
    assert TwinNoteServingService(db_path=db).composition("__operator__", made["composition_id"])


@pytest.mark.parametrize("malformation", ["partial", "index", "constraint"])
def test_v22_populated_malformed_shapes_fail_without_mutation(tmp_path, malformation):
    db = str(tmp_path / f"{malformation}.duckdb"); init_database_at_path(db)
    with connect_write(db, purpose="test/c48-malformed-v22") as con:
        if malformation == "partial":
            con.execute("DROP TABLE twin_note_composition_members")
            con.execute("INSERT INTO twin_note_compositions VALUES ('x','owner',1,'sha','blob','hash',2,CURRENT_TIMESTAMP)")
        elif malformation == "index":
            con.execute("DROP INDEX idx_twin_note_compositions_owner")
            con.execute("INSERT INTO twin_note_compositions VALUES ('x','owner',1,'sha','blob','hash',2,CURRENT_TIMESTAMP)")
        else:
            con.execute("DROP TABLE twin_note_composition_members"); con.execute("DROP TABLE twin_note_compositions")
            con.execute("CREATE TABLE twin_note_compositions(composition_id TEXT)")
            con.execute("INSERT INTO twin_note_compositions VALUES ('occupied')")
    from substrate.graph.schema import _INITIALIZED_PATHS
    _INITIALIZED_PATHS.discard(db); before = _v22_snapshot(db)
    with pytest.raises(RuntimeError): init_database_at_path(db)
    assert _v22_snapshot(db) == before
