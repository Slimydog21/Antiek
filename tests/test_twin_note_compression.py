from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.twin_note_taker.compression import (
    DurableTwinNoteCompression,
    TwinNoteCompressionError,
)


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _window(db, window_id, investigation_id, ordinal, text):
    sources = [f"evt-{investigation_id}-{ordinal}"]
    source_json = _canon(sources)
    request_json = _canon({"document_id": "untrusted-metadata", "investigation_id": investigation_id,
                           "source_event_ids": sources})
    raw = _canon({"notes": [{"text": text, "confidence": "high", "source_event_ids": sources}]})
    with connect_write(db, purpose="test/compression-seed") as con:
        con.execute("INSERT INTO note_taker_windows (window_id,consumer_version,investigation_id,threshold,ordinal,first_event_id,last_event_id,source_event_ids_json,source_digest,request_json,request_sha256,provider_idempotency_key,state,raw_result,raw_result_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [window_id, 2, investigation_id, 5, ordinal, sources[0], sources[-1], source_json, _sha(source_json), request_json, _sha(request_json), window_id, "completed", raw, _sha(raw)])


@pytest.fixture
def setup(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _window(db, "w-a", "inv-a", 0, "Alpha")
    _window(db, "w-b", "inv-b", 0, "Beta")
    events = tmp_path / "events"
    events.mkdir()
    resolver = lambda account, asset, investigation: account == "acct" and asset == "asset" and investigation in {"inv-a", "inv-b"}
    return db, tmp_path / "published", events, resolver


def _service(setup, checkpoint=None):
    db, published, events, resolver = setup
    return DurableTwinNoteCompression(resolver, db_path=db, publication_root=published,
                                      events_dir=str(events), checkpoint=checkpoint)


def _process_compress(db, published, events, ids, predecessor, result_file):
    resolver = lambda account, asset, investigation: account == "acct" and asset == "asset"
    service = DurableTwinNoteCompression(resolver, db_path=db, publication_root=published, events_dir=events)
    try:
        revision = service.compress(account_id="acct", asset_id="asset", window_ids=tuple(ids), expected_predecessor=predecessor)
        Path(result_file).write_text("ok:" + revision.revision_id)
    except Exception as exc:
        Path(result_file).write_text("error:" + type(exc).__name__)


def _process_die_at_checkpoint(db, published, events, death_checkpoint):
    resolver = lambda account, asset, investigation: True
    def checkpoint(name, _identity):
        if name == death_checkpoint:
            os._exit(73)
    DurableTwinNoteCompression(resolver, db_path=db, publication_root=published,
        events_dir=events, checkpoint=checkpoint).compress(
            account_id="acct", asset_id="asset", window_ids=("w-a",))


def test_order_is_identity_and_html_is_static_attributed(setup):
    service = _service(setup)
    ab = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a", "w-b"))
    ba = service.compress(account_id="acct", asset_id="asset", window_ids=("w-b", "w-a"),
                          expected_predecessor=ab.revision_id)
    assert ab.revision_id != ba.revision_id
    page = ba.html_bytes.decode()
    assert page.index("Beta") < page.index("Alpha")
    assert "inv-b" in page and "evt-inv-b-0" in page
    assert "<textarea" not in page and "<script>" not in page and "Date" not in page


def test_exact_retry_is_byte_identical_and_singleton(setup):
    service = _service(setup)
    one = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    two = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    assert one == two
    with connect_read(setup[0]) as con:
        assert con.execute("SELECT COUNT(*) FROM twin_note_revisions").fetchone() == (1,)
        assert con.execute("SELECT COUNT(*) FROM write_event_outbox WHERE aggregate_kind='twin_note_revision'").fetchone() == (1,)
    assert len(list(setup[1].rglob("*.html"))) == 1


@pytest.mark.parametrize("mutation", ["state", "raw", "request", "source"])
def test_corrupt_or_incomplete_member_fails_before_insert(setup, mutation):
    with connect_write(setup[0], purpose="test/corrupt") as con:
        if mutation == "state":
            con.execute("UPDATE note_taker_windows SET state='materialized' WHERE window_id='w-a'")
        elif mutation == "raw":
            con.execute("UPDATE note_taker_windows SET raw_result='changed' WHERE window_id='w-a'")
        elif mutation == "request":
            con.execute("UPDATE note_taker_windows SET request_json='{}' WHERE window_id='w-a'")
        else:
            con.execute("UPDATE note_taker_windows SET source_event_ids_json='[]' WHERE window_id='w-a'")
    with pytest.raises(TwinNoteCompressionError):
        _service(setup).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_read(setup[0]) as con:
        assert con.execute("SELECT COUNT(*) FROM twin_note_revisions").fetchone() == (0,)


@pytest.mark.parametrize("field,value", [
    ("investigation_id", "inv-hostile"),
    ("source_event_ids", ["evt-hostile"]),
])
def test_rehashed_request_must_match_window_bindings(setup, field, value):
    with connect_write(setup[0], purpose="test/request-binding") as con:
        request = json.loads(con.execute(
            "SELECT request_json FROM note_taker_windows WHERE window_id='w-a'"
        ).fetchone()[0])
        request[field] = value
        request_json = _canon(request)
        con.execute(
            "UPDATE note_taker_windows SET request_json=?,request_sha256=? WHERE window_id='w-a'",
            [request_json, _sha(request_json)],
        )
    with pytest.raises(TwinNoteCompressionError, match="bound"):
        _service(setup).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_read(setup[0]) as con:
        assert con.execute("SELECT COUNT(*) FROM twin_note_revisions").fetchone() == (0,)


def test_ownership_and_stale_predecessor_fail_closed(setup):
    service = _service(setup)
    with pytest.raises(TwinNoteCompressionError, match="ownership"):
        service.compress(account_id="other", asset_id="asset", window_ids=("w-a",))
    first = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    second = service.compress(account_id="acct", asset_id="asset", window_ids=("w-b",), expected_predecessor=first.revision_id)
    with pytest.raises(TwinNoteCompressionError, match="stale"):
        service.compress(account_id="acct", asset_id="asset", window_ids=("w-a", "w-b"), expected_predecessor=first.revision_id)
    assert service.current_revision(account_id="acct", asset_id="asset").revision_id == second.revision_id


@pytest.mark.parametrize("checkpoint", ["after_transaction_commit", "after_temporary_write", "after_file_fsync", "after_link", "after_directory_fsync", "after_publication_receipt", "after_append", "before_receipt"])
def test_every_crash_checkpoint_recovers(setup, checkpoint):
    crashed = False
    def stop(name, _identity):
        nonlocal crashed
        if not crashed and name == checkpoint:
            crashed = True
            raise RuntimeError("crash")
    with pytest.raises(RuntimeError, match="crash"):
        _service(setup, stop).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    service = _service(setup)
    service.recover()
    retry = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    assert (setup[1] / retry.relative_path).read_bytes() == retry.html_bytes
    with connect_read(setup[0]) as con:
        assert con.execute("SELECT state FROM twin_note_publication_effects").fetchone() == ("published",)
        assert con.execute("SELECT state FROM write_event_outbox WHERE aggregate_kind='twin_note_revision'").fetchone() == ("delivered",)


def test_conflicting_final_bytes_fail_closed(setup):
    def stop(name, _identity):
        if name == "after_transaction_commit":
            raise RuntimeError("stop")
    with pytest.raises(RuntimeError):
        _service(setup, stop).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_read(setup[0]) as con:
        relative = con.execute("SELECT relative_path FROM twin_note_revisions").fetchone()[0]
    path = setup[1] / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"hostile")
    with pytest.raises(TwinNoteCompressionError, match="conflicting"):
        _service(setup).recover()


def test_concurrent_process_successors_allow_exactly_one(setup):
    first = _service(setup).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    ctx = multiprocessing.get_context("fork")
    outputs = [str(Path(setup[1]).parent / f"result-{index}") for index in range(2)]
    processes = [ctx.Process(target=_process_compress, args=(setup[0], str(setup[1]), str(setup[2]), ids, first.revision_id, output))
                 for ids, output in zip((("w-b",), ("w-a", "w-b")), outputs)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    results = [Path(output).read_text() for output in outputs]
    assert sum(result.startswith("ok:") for result in results) == 1
    assert sum(result.startswith("error:") for result in results) == 1
    with connect_read(setup[0]) as con:
        assert con.execute("SELECT COUNT(*) FROM twin_note_revisions").fetchone() == (2,)


@pytest.mark.parametrize("death_checkpoint", ["after_temporary_write", "after_file_fsync", "after_link", "after_directory_fsync"])
def test_real_process_death_during_publication_recovers_exactly(setup, death_checkpoint):
    ctx = multiprocessing.get_context("fork")
    child = ctx.Process(target=_process_die_at_checkpoint,
                        args=(setup[0], str(setup[1]), str(setup[2]), death_checkpoint))
    child.start()
    child.join(10)
    assert child.exitcode == 73
    service = _service(setup)
    service.recover()
    revision = service.current_revision(account_id="acct", asset_id="asset")
    assert revision is not None
    assert (setup[1] / revision.relative_path).read_bytes() == revision.html_bytes
    assert not list(setup[1].rglob("*.tmp"))


def test_empty_partial_v21_repairs_and_populated_fails(setup):
    db = setup[0]
    from substrate.graph.schema import init_database
    with connect_write(db, purpose="test/v21") as con:
        for table in ("twin_note_publication_effects", "twin_note_revision_members", "twin_note_revisions"):
            con.execute(f"DROP TABLE {table}")
        con.execute("CREATE TABLE twin_note_revisions (revision_id TEXT)")
        init_database(con)
        con.execute("DROP TABLE twin_note_publication_effects")
        con.execute("DROP TABLE twin_note_revision_members")
        con.execute("DROP TABLE twin_note_revisions")
        con.execute("CREATE TABLE twin_note_revisions (revision_id TEXT)")
        con.execute("INSERT INTO twin_note_revisions VALUES ('occupied')")
        with pytest.raises(RuntimeError, match="populated partial V21"):
            init_database(con)


def test_valid_populated_v21_reopens_with_same_named_auxiliary_schema(setup):
    from substrate.graph.schema import init_database
    revision = _service(setup).compress(
        account_id="acct", asset_id="asset", window_ids=("w-a",)
    )
    with connect_write(setup[0], purpose="test/v21-aux-schema") as con:
        con.execute("CREATE SCHEMA auxiliary")
        con.execute("CREATE TABLE auxiliary.twin_note_revisions (revision_id TEXT PRIMARY KEY)")
        init_database(con)
        assert con.execute(
            "SELECT revision_id FROM main.twin_note_revisions"
        ).fetchone() == (revision.revision_id,)


def test_populated_v21_missing_index_fails_without_mutation(setup):
    from substrate.graph.schema import init_database
    revision = _service(setup).compress(
        account_id="acct", asset_id="asset", window_ids=("w-a",)
    )
    with connect_write(setup[0], purpose="test/v21-missing-index") as con:
        con.execute("DROP INDEX idx_twin_note_effects_pending")
        before = con.execute("SELECT * FROM twin_note_revisions").fetchall()
        with pytest.raises(RuntimeError, match="populated partial V21"):
            init_database(con)
        assert con.execute("SELECT * FROM twin_note_revisions").fetchall() == before
        assert con.execute(
            "SELECT COUNT(*) FROM duckdb_indexes() WHERE schema_name='main' "
            "AND index_name='idx_twin_note_effects_pending'"
        ).fetchone() == (0,)


def test_partial_owned_temp_is_replaced_from_db_bytes(setup):
    def stop(name, _identity):
        if name == "after_transaction_commit":
            raise RuntimeError("stop")
    with pytest.raises(RuntimeError):
        _service(setup, stop).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_read(setup[0]) as con:
        effect_id, relative = con.execute(
            "SELECT effect_id,expected_path FROM twin_note_publication_effects"
        ).fetchone()
    parent = setup[1] / Path(relative).parent
    parent.mkdir(parents=True)
    (parent / f".{effect_id}.tmp").write_bytes(b"truncated")
    _service(setup).recover()
    revision = _service(setup).current_revision(account_id="acct", asset_id="asset")
    assert (setup[1] / relative).read_bytes() == revision.html_bytes
    assert not list(setup[1].rglob("*.tmp"))


@pytest.mark.parametrize("damage", ["delete", "corrupt", "hardlink"])
def test_recovery_audits_already_published_final(setup, damage):
    service = _service(setup)
    revision = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    final = setup[1] / revision.relative_path
    if damage == "delete":
        final.unlink()
        service.recover(revision_id=revision.revision_id)
        assert final.read_bytes() == revision.html_bytes
    elif damage == "corrupt":
        final.write_bytes(b"corrupt")
        with pytest.raises(TwinNoteCompressionError, match="conflicting"):
            service.recover(revision_id=revision.revision_id)
    else:
        os.link(final, final.with_suffix(".alias"))
        with pytest.raises(TwinNoteCompressionError, match="singly-linked"):
            service.recover(revision_id=revision.revision_id)


def test_symlink_final_and_non_owned_temp_fail_closed(setup):
    def stop(name, _identity):
        if name == "after_transaction_commit":
            raise RuntimeError("stop")
    with pytest.raises(RuntimeError):
        _service(setup, stop).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_read(setup[0]) as con:
        effect_id, relative = con.execute(
            "SELECT effect_id,expected_path FROM twin_note_publication_effects"
        ).fetchone()
    parent = setup[1] / Path(relative).parent
    parent.mkdir(parents=True)
    hostile = parent / "hostile"
    hostile.write_bytes(b"hostile")
    (setup[1] / relative).symlink_to(hostile)
    with pytest.raises(TwinNoteCompressionError, match="nofollow"):
        _service(setup).recover()
    (setup[1] / relative).unlink()
    (parent / f".{effect_id}.tmp").symlink_to(hostile)
    with pytest.raises(TwinNoteCompressionError, match="non-owned"):
        _service(setup).recover()


def test_resolver_can_access_database_outside_writer_lock(setup):
    db, published, events, _ = setup
    def resolver(account, asset, investigation):
        with connect_read(db) as con:
            found = con.execute(
                "SELECT COUNT(*) FROM note_taker_windows WHERE investigation_id=?", [investigation]
            ).fetchone()[0]
        return account == "acct" and asset == "asset" and found == 1
    revision = DurableTwinNoteCompression(
        resolver, db_path=db, publication_root=published, events_dir=str(events)
    ).compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    assert revision.revision_id.startswith("tnr-")


def test_exact_retry_rejects_created_at_mutation(setup):
    service = _service(setup)
    revision = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    with connect_write(setup[0], purpose="test/mutate-created-at") as con:
        # DuckDB conservatively blocks updates to any referenced parent row;
        # remove the children so this test can model offline DB corruption.
        con.execute("DELETE FROM twin_note_publication_effects WHERE revision_id=?", [revision.revision_id])
        con.execute("DELETE FROM twin_note_revision_members WHERE revision_id=?", [revision.revision_id])
        con.execute(
            "UPDATE twin_note_revisions SET created_at=created_at + INTERVAL 1 SECOND WHERE revision_id=?",
            [revision.revision_id],
        )
    with pytest.raises(TwinNoteCompressionError, match="immutable"):
        service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))


def test_database_rejects_direct_second_successor(setup):
    service = _service(setup)
    first = service.compress(account_id="acct", asset_id="asset", window_ids=("w-a",))
    service.compress(account_id="acct", asset_id="asset", window_ids=("w-b",),
                     expected_predecessor=first.revision_id)
    with connect_write(setup[0], purpose="test/direct-fork") as con:
        with pytest.raises(Exception, match="[Uu]nique|[Cc]onstraint"):
            con.execute(
                "INSERT INTO twin_note_revisions SELECT 'hostile-fork',account_id,asset_id,"
                "supersedes_revision_id,compressor_version,renderer_version,'other-membership',"
                "body_json,body_sha256,html_bytes,html_sha256,'other/path/file.html',note_count,"
                "source_event_count,created_at FROM twin_note_revisions WHERE supersedes_revision_id=?",
                [first.revision_id],
            )


def test_member_and_effect_orphans_are_rejected(setup):
    with connect_write(setup[0], purpose="test/orphans") as con:
        with pytest.raises(Exception, match="[Ff]oreign|[Cc]onstraint"):
            con.execute(
                "INSERT INTO twin_note_revision_members VALUES "
                "('missing',0,'inv-a','w-a',2,0,'digest','raw')"
            )
        with pytest.raises(Exception, match="[Ff]oreign|[Cc]onstraint"):
            con.execute(
                "INSERT INTO twin_note_publication_effects "
                "(effect_id,revision_id,expected_path,expected_sha256) "
                "VALUES ('effect','missing','a/b/c','digest')"
            )
