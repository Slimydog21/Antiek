from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from processing.embedding import _reset_default_provider
from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.event_log import iter_physical_events, seal_investigation
from substrate.graph import knowledge_event_projector as projector
from substrate.graph.schema import (
    SchemaCorruptionError,
    init_database,
    init_database_at_path,
)


def _event(event_id: str, action_type: str, text: str, emitted_at: str) -> dict:
    field = "question_text" if action_type == "question.identified" else "note_text"
    return {
        "event_id": event_id,
        "investigation_id": "inv-1",
        "action_type": action_type,
        "payload": {field: text},
        "emitted_at": emitted_at,
    }


def _write_tail(path: Path, rows: list[dict], *, complete: bool = True) -> None:
    data = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    if not complete and data:
        data = data[:-1]
    path.write_bytes(data)


@pytest.fixture
def graph_db(tmp_path: Path) -> str:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    return path


@pytest.fixture(autouse=True)
def deterministic_embeddings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep replay tests offline and independent of model cold-start time."""
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    yield
    _reset_default_provider()


def test_physical_snapshot_then_tail_order_and_cross_layer_duplicate(
    graph_db: str, tmp_path: Path
) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    first = _event("evt-first", "note.emerged", "first", "2030-01-01T00:00:00Z")
    second = _event("evt-second", "question.identified", "second?", "2020-01-01T00:00:00Z")
    pq.write_table(pa.Table.from_pylist([first, second]), events_dir / "inv-1.parquet")
    third = _event("evt-third", "note.emerged", "third", "2010-01-01T00:00:00Z")
    _write_tail(events_dir / "inv-1.jsonl", [first, third])

    rows = list(iter_physical_events("inv-1", events_dir=str(events_dir)))

    assert [row["event_id"] for row in rows] == [
        "evt-first", "evt-second", "evt-first", "evt-third"
    ]
    report = projector.recover(db_path=graph_db, events_dir=str(events_dir))
    assert report.succeeded == 3
    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 3
    finally:
        con.close()


def test_reseal_preserves_snapshot_then_tail_order_with_regressing_timestamps(
    tmp_path: Path,
) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    first = _event("evt-first", "note.emerged", "first", "2030")
    second = _event("evt-second", "note.emerged", "second", "2020")
    third = _event("evt-third", "note.emerged", "third", "2010")
    pq.write_table(pa.Table.from_pylist([first, second]), events_dir / "inv-1.parquet")
    _write_tail(events_dir / "inv-1.jsonl", [third])

    seal_investigation(
        "inv-1",
        events_dir=str(events_dir),
        outbox_db_path=None,
    )

    rows = list(iter_physical_events("inv-1", events_dir=str(events_dir)))
    assert [row["event_id"] for row in rows] == ["evt-first", "evt-second", "evt-third"]


def test_optional_field_normalization_survives_tail_seal_receipt_replay(
    graph_db: str, tmp_path: Path
) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    target = _event("evt-target", "note.emerged", "stable", "2020")
    heterogeneous = _event("evt-other", "note.emerged", "other", "2021")
    heterogeneous["payload"]["optional_context"] = {"source": "book"}
    pq.write_table(
        pa.Table.from_pylist([target, heterogeneous]), events_dir / "inv-1.parquet"
    )
    _write_tail(events_dir / "inv-1.jsonl", [target])

    first = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), wall_time_s=5
    )
    assert first.succeeded == 2
    seal_investigation("inv-1", events_dir=str(events_dir), outbox_db_path=None)
    replay = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), wall_time_s=5
    )
    # A changed snapshot generation examines exactly the anchor row, not the
    # payload prefix, before proving the resealed trajectory is exhausted.
    assert replay.scanned == 3


def test_unterminated_tail_is_not_consumed_and_malformed_complete_line_fails(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    tail = events_dir / "inv-1.jsonl"
    _write_tail(tail, [_event("evt-1", "note.emerged", "one", "2020")], complete=False)
    assert list(iter_physical_events("inv-1", events_dir=str(events_dir))) == []

    tail.write_bytes(b"{not-json}\n")
    with pytest.raises(RuntimeError, match="malformed completed JSONL"):
        list(iter_physical_events("inv-1", events_dir=str(events_dir)))


def test_reseal_refuses_and_preserves_incomplete_tail(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    tail = events_dir / "inv-1.jsonl"
    _write_tail(tail, [_event("evt-incomplete", "note.emerged", "one", "2020")], complete=False)
    original = tail.read_bytes()

    with pytest.raises(RuntimeError, match="cannot seal an incomplete JSONL append"):
        seal_investigation(
            "inv-1",
            events_dir=str(events_dir),
            outbox_db_path=None,
        )

    assert tail.read_bytes() == original
    assert not (events_dir / "inv-1.parquet").exists()


def test_poison_is_quarantined_and_later_event_projects(graph_db: str, tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    poison = _event("evt-poison", "note.emerged", "ignored", "2020")
    poison["payload"] = {"note_text": ""}
    valid = _event("evt-valid", "question.identified", "What remains?", "2019")
    _write_tail(events_dir / "inv-1.jsonl", [poison, valid])

    report = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), wall_time_s=10
    )

    assert (report.quarantined, report.succeeded, report.catching_up) == (1, 1, False)
    con = duckdb.connect(graph_db, read_only=True)
    try:
        rows = con.execute(
            "SELECT event_id, status, error_class, error_digest FROM event_consumer_receipts "
            "ORDER BY event_id"
        ).fetchall()
    finally:
        con.close()
    assert rows[0][0:3] == ("evt-poison", "quarantined", "LegacyEventPayloadError")
    assert len(rows[0][3]) == 64
    assert rows[1][0:2] == ("evt-valid", "succeeded")


def test_projection_and_receipt_roll_back_atomically(
    graph_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    event = _event("evt-atomic", "note.emerged", "atomic", "2020")
    _write_tail(events_dir / "inv-1.jsonl", [event])

    def fail_after_write(event: dict, *, con, **_: object) -> None:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('node-partial', 'partial', 'insight', 'depth')"
        )
        raise RuntimeError("infrastructure failure")

    monkeypatch.setitem(projector._ACTIONS, "note.emerged", fail_after_write)
    with pytest.raises(RuntimeError, match="infrastructure failure"):
        projector.recover(db_path=graph_db, events_dir=str(events_dir))

    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM nodes WHERE node_id='node-partial'").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 0
    finally:
        con.close()


def test_bounded_recovery_then_drain(graph_db: str, tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    rows = [_event(f"evt-{index}", "note.emerged", f"note {index}", "2020") for index in range(5)]
    _write_tail(events_dir / "inv-1.jsonl", rows)

    first = projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        candidate_limit=2,
        wall_time_s=10,
    )
    assert (first.succeeded, first.catching_up, first.remaining) == (2, True, None)

    final = projector.drain(
        db_path=graph_db,
        events_dir=str(events_dir),
        batch_size=2,
        wall_time_s=10,
    )
    assert (final.succeeded, final.catching_up, final.remaining) == (3, False, 0)
    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 5
    finally:
        con.close()


def test_frontier_snapshot_releases_writer_lock_between_bounded_pages(
    graph_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    with connect_write(graph_db, purpose="test/frontier-pages") as con:
        for index in range(3):
            (events_dir / f"inv-{index}.jsonl").touch()
            con.execute(
                "INSERT INTO event_consumer_frontiers "
                "(consumer_name, consumer_version, investigation_id, next_ordinal) "
                "VALUES (?, ?, ?, 0)",
                [projector.CONSUMER_NAME, projector.CONSUMER_VERSION, f"inv-{index}"],
            )

    original = projector._connect_write_with_handoff_retry
    snapshot_pages: list[str] = []

    def observed_connect(db_path: str, *, purpose: str, deadline: float):
        if purpose == "knowledge_event_frontier_snapshot_page":
            snapshot_pages.append(purpose)
        return original(db_path, purpose=purpose, deadline=deadline)

    monkeypatch.setattr(projector, "_connect_write_with_handoff_retry", observed_connect)
    report = projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        candidate_limit=2,
        wall_time_s=10,
    )
    assert not report.catching_up
    assert snapshot_pages == [
        "knowledge_event_frontier_snapshot_page",
        "knowledge_event_frontier_snapshot_page",
    ]


def test_v19_repairs_empty_partial_and_rejects_populated_partial(tmp_path: Path) -> None:
    empty_path = str(tmp_path / "empty.duckdb")
    init_database_at_path(empty_path)
    with connect_write(empty_path, purpose="test_partial_v19") as con:
        con.execute("DROP TABLE event_consumer_receipts")
        con.execute("CREATE TABLE event_consumer_receipts (event_id TEXT)")
        init_database(con)
        assert len(con.execute("DESCRIBE event_consumer_receipts").fetchall()) == 12

    populated_path = str(tmp_path / "populated.duckdb")
    init_database_at_path(populated_path)
    with connect_write(populated_path, purpose="test_partial_v19") as con:
        con.execute("DROP TABLE event_consumer_receipts")
        con.execute("CREATE TABLE event_consumer_receipts (event_id TEXT)")
        con.execute("INSERT INTO event_consumer_receipts VALUES ('evt-existing')")
        with pytest.raises(RuntimeError, match="populated partial V19"):
            init_database(con)

    invalid_path = str(tmp_path / "invalid.duckdb")
    init_database_at_path(invalid_path)
    with connect_write(invalid_path, purpose="test_invalid_v19") as con:
        con.execute("DROP TABLE event_consumer_receipts")
        con.execute(
            "CREATE TABLE event_consumer_receipts ("
            "consumer_name TEXT, consumer_version INTEGER, investigation_id TEXT, "
            "event_id TEXT, action_type TEXT, event_sha256 TEXT, status TEXT, "
            "output_ref TEXT, error_class TEXT, error_digest TEXT, "
            "attempt_count INTEGER, processed_at TIMESTAMP)"
        )
        con.execute(
            "INSERT INTO event_consumer_receipts VALUES "
            "('c', 1, 'i', 'e', 'a', 'h', 'succeeded', NULL, NULL, NULL, 1, now())"
        )
        with pytest.raises(RuntimeError, match="populated partial V19"):
            init_database(con)


def test_conflicting_duplicate_event_identity_fails_closed(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    rows = [
        _event("evt-same", "note.emerged", "first bytes", "2020"),
        _event("evt-same", "note.emerged", "different bytes", "2020"),
    ]
    _write_tail(events_dir / "inv-1.jsonl", rows)
    with pytest.raises(RuntimeError, match="event identity conflict"):
        projector.recover(db_path=graph_db, events_dir=str(events_dir), candidate_limit=2)


def test_identical_duplicate_split_advances_cursor_without_new_ordinal(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    event = _event("evt-duplicate", "note.emerged", "same", "2020")
    _write_tail(events_dir / "inv-1.jsonl", [event, event])

    first = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), candidate_limit=1
    )
    second = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), candidate_limit=1
    )

    assert (first.succeeded, second.already_received) == (1, 1)
    with duckdb.connect(graph_db, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM event_consumer_events").fetchone() == (1,)
        assert con.execute(
            "SELECT next_ordinal, jsonl_byte_offset FROM event_consumer_frontiers"
        ).fetchone() == (1, (events_dir / "inv-1.jsonl").stat().st_size)


def test_unsupported_event_gets_authority_without_receipt(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    event = _event("evt-unsupported", "worker.started", "ignored", "2020")
    _write_tail(events_dir / "inv-1.jsonl", [event])

    projector.recover(db_path=graph_db, events_dir=str(events_dir))

    with duckdb.connect(graph_db, read_only=True) as con:
        assert con.execute(
            "SELECT logical_ordinal, resolution FROM event_consumer_events"
        ).fetchone() == (0, "unsupported")
        assert con.execute("SELECT count(*) FROM event_consumer_receipts").fetchone() == (0,)


def test_missing_action_type_fails_closed(graph_db: str, tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    event = _event("evt-no-action", "note.emerged", "invalid", "2030")
    event.pop("action_type")
    _write_tail(events_dir / "inv-1.jsonl", [event])

    with pytest.raises(projector.EventConsumerCorruption, match="invalid action_type"):
        projector.recover(db_path=graph_db, events_dir=str(events_dir), wall_time_s=5)


def test_startup_worker_polls_for_tail_completed_after_startup(
    graph_db: str, monkeypatch, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    tail = events_dir / "inv-1.jsonl"
    event = _event("evt-late-complete", "note.emerged", "eventual", "2030")
    _write_tail(tail, [event], complete=False)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", graph_db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])

    with TestClient(app):
        deadline = time.monotonic() + 3
        while app.state.knowledge_event_recovery["status"] != "current":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        with tail.open("ab") as stream:
            stream.write(b"\n")
        while True:
            with duckdb.connect(graph_db) as con:
                if con.execute(
                    "SELECT count(*) FROM event_consumer_events WHERE event_id=?",
                    [event["event_id"]],
                ).fetchone() == (1,):
                    break
            assert time.monotonic() < deadline
            time.sleep(0.05)


def test_distinct_events_with_same_text_keep_distinct_receipts(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [
            _event("evt-a", "note.emerged", "same insight", "2020"),
            _event("evt-b", "note.emerged", "same insight", "2021"),
        ],
    )
    report = projector.recover(
        db_path=graph_db, events_dir=str(events_dir), wall_time_s=10
    )
    assert report.succeeded == 2
    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
    finally:
        con.close()


def test_received_event_with_changed_bytes_fails_closed(graph_db: str, tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    tail = events_dir / "inv-1.jsonl"
    _write_tail(tail, [_event("evt-mutated", "note.emerged", "original", "2020")])
    assert projector.recover(db_path=graph_db, events_dir=str(events_dir)).succeeded == 1
    _write_tail(tail, [_event("evt-mutated", "note.emerged", "changed", "2020")])

    with pytest.raises(RuntimeError, match="tail cursor is beyond EOF"):
        projector.recover(db_path=graph_db, events_dir=str(events_dir))


def test_linked_event_file_is_rejected(graph_db: str, tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    outside = tmp_path / "outside.jsonl"
    _write_tail(outside, [_event("evt-linked", "note.emerged", "linked", "2020")])
    (events_dir / "inv-1.jsonl").symlink_to(outside)
    with pytest.raises(RuntimeError, match="unsafe event file"):
        projector.recover(db_path=graph_db, events_dir=str(events_dir))


def _recovery_child(db: str, events: Path, crash_boundary: str | None = None):
    code = textwrap.dedent(
        f"""
        import os
        from substrate.graph.knowledge_event_projector import recover
        def checkpoint(boundary, event_id):
            if boundary == {crash_boundary!r}:
                os._exit(73)
        recover(
            db_path={db!r},
            events_dir={str(events)!r},
            checkpoint=checkpoint,
        )
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    env["ANTIEK_EMBEDDING_PROVIDER"] = "hash"
    return subprocess.Popen([sys.executable, "-c", code], env=env)


def _fresh_process_counts(db: str) -> tuple[int, int]:
    code = textwrap.dedent(
        f"""
        import json
        import duckdb
        con = duckdb.connect({db!r}, read_only=True)
        print(json.dumps([
            con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM nodes WHERE node_type='insight'").fetchone()[0],
        ]))
        """
    )
    output = subprocess.check_output([sys.executable, "-c", code], text=True)
    receipt_count, node_count = json.loads(output)
    return receipt_count, node_count


def test_real_process_death_before_receipt_recovers_exactly_once(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-crash", "note.emerged", "survives process death", "2020")],
    )
    child = _recovery_child(graph_db, events_dir, "after_projection_before_receipt")
    assert child.wait(timeout=20) == 73
    report = projector.recover(db_path=graph_db, events_dir=str(events_dir))
    assert report.succeeded + report.already_received == 1
    assert _fresh_process_counts(graph_db) == (1, 1)


def test_real_process_death_after_commit_is_restart_visible(tmp_path: Path) -> None:
    db = str(tmp_path / "crash.duckdb")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-crash", "note.emerged", "survives process death", "2020")],
    )
    crash_code = textwrap.dedent(
        f"""
        import os
        from substrate.graph.knowledge_event_projector import recover
        recover(
            db_path={db!r},
            events_dir={str(events_dir)!r},
            checkpoint=lambda boundary, event_id: os._exit(73)
                if boundary == "after_commit" else None,
        )
        """
    )
    creator = "\n".join(
        [
            "import os, subprocess, sys",
            "from substrate.graph.schema import init_database_at_path",
            f"init_database_at_path({db!r})",
            "env = dict(os.environ)",
            'env["ANTIEK_EMBEDDING_PROVIDER"] = "hash"',
            f"result = subprocess.run([sys.executable, '-c', {crash_code!r}], env=env)",
            "raise SystemExit(0 if result.returncode == 73 else 1)",
        ]
    )
    subprocess.run([sys.executable, "-c", creator], check=True)
    assert _fresh_process_counts(db) == (1, 1)


def test_two_processes_racing_one_event_commit_one_receipt(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-race", "question.identified", "Who wins?", "2020")],
    )
    children = [_recovery_child(graph_db, events_dir) for _ in range(2)]
    assert [child.wait(timeout=20) for child in children] == [0, 0]
    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM nodes WHERE node_type='question'").fetchone()[0] == 1
    finally:
        con.close()


def test_app_startup_recovers_pending_knowledge_event(tmp_path: Path, monkeypatch) -> None:
    db = str(tmp_path / "startup.duckdb")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    init_database_at_path(db)
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-startup", "question.identified", "What changed?", "2020")],
    )
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])

    with TestClient(app):
        deadline = time.monotonic() + 3
        while app.state.knowledge_event_recovery["status"] == "catching_up":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        state = app.state.knowledge_event_recovery

    assert state["status"] == "current"
    assert state["succeeded"] == 1
    con = duckdb.connect(db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 1
    finally:
        con.close()


def test_app_startup_does_not_create_missing_db_and_retries_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    db = str(tmp_path / "missing.duckdb")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-fresh", "note.emerged", "fresh database", "2020")],
    )
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    started = time.monotonic()

    with TestClient(app):
        assert time.monotonic() - started < 1.0
        deadline = time.monotonic() + 1
        while app.state.knowledge_event_recovery["status"] != "retrying":
            assert time.monotonic() < deadline
            time.sleep(0.01)

    assert not os.path.exists(db)
    assert app.state.knowledge_event_recovery["status"] == "retrying"
    assert app.state.knowledge_event_recovery["error_class"] == "SchemaUnavailableError"


def test_app_startup_worker_continues_catch_up_batches(monkeypatch, tmp_path: Path) -> None:
    import runtime.db_lock as db_lock_module

    calls = 0
    call_times: list[float] = []
    db_path = str(tmp_path / "worker.duckdb")
    handoff_checks = 0

    def handoff_requested(_db_path: str) -> bool:
        nonlocal handoff_checks
        handoff_checks += 1
        return handoff_checks == 2

    def fake_recover(**_: object) -> projector.RecoveryReport:
        nonlocal calls
        calls += 1
        call_times.append(time.monotonic())
        time.sleep(0.15)
        return projector.RecoveryReport(catching_up=calls == 1, remaining=None)

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setattr(db_lock_module, "write_handoff_requested", handoff_requested)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    started = time.monotonic()
    with TestClient(app):
        assert time.monotonic() - started < 0.14
        deadline = time.monotonic() + 2
        while app.state.knowledge_event_recovery["status"] == "catching_up":
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert calls == 2
    assert call_times[1] - call_times[0] >= 0.6
    assert app.state.knowledge_event_recovery["status"] == "current"


def test_app_startup_worker_retries_transient_then_recovers(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_recover(**_: object) -> projector.RecoveryReport:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise duckdb.IOException("temporary lock handoff")
        return projector.RecoveryReport()

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "retry.duckdb"))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app):
        deadline = time.monotonic() + 2
        while app.state.knowledge_event_recovery["status"] != "current":
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert calls == 3


def test_app_startup_worker_stops_on_terminal_corruption(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_recover(**_: object) -> projector.RecoveryReport:
        nonlocal calls
        calls += 1
        raise projector.EventConsumerCorruption("immutable conflict")

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "corrupt.duckdb"))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app):
        deadline = time.monotonic() + 1
        while app.state.knowledge_event_recovery["status"] == "catching_up":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert app.state.knowledge_event_recovery["terminal"] is True
    assert calls == 1


def test_app_startup_worker_stops_on_terminal_schema_corruption(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_recover(**_: object) -> projector.RecoveryReport:
        raise SchemaCorruptionError("populated partial V19 receipts")

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "schema-corrupt.duckdb"))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app):
        deadline = time.monotonic() + 1
        while app.state.knowledge_event_recovery["status"] == "catching_up":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert app.state.knowledge_event_recovery["terminal"] is True


def test_app_shutdown_interrupts_transient_retry_backoff(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_recover(**_: object) -> projector.RecoveryReport:
        nonlocal calls
        calls += 1
        raise duckdb.IOException("still unavailable")

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "shutdown.duckdb"))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app):
        deadline = time.monotonic() + 1
        while app.state.knowledge_event_recovery["status"] != "retrying":
            assert time.monotonic() < deadline
            time.sleep(0.01)
    calls_after_shutdown = calls
    time.sleep(0.1)
    assert calls == calls_after_shutdown
    assert not app.state.knowledge_event_recovery_worker.is_alive()


def test_app_shutdown_is_bounded_when_recovery_provider_does_not_exit(
    monkeypatch, tmp_path: Path
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def fake_recover(**kwargs: object) -> projector.RecoveryReport:
        entered.set()
        should_stop = kwargs["should_stop"]
        assert callable(should_stop)
        while not should_stop():
            time.sleep(0.01)
        release.wait(5)
        return projector.RecoveryReport(catching_up=True, remaining=None)

    monkeypatch.setattr(projector, "recover", fake_recover)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "owned.duckdb"))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    started_shutdown = 0.0
    with TestClient(app):
        deadline = time.monotonic() + 1
        assert entered.wait(max(0.0, deadline - time.monotonic()))
        started_shutdown = time.monotonic()

    assert time.monotonic() - started_shutdown < 1.5
    assert app.state.knowledge_event_recovery["status"] == "stopping"
    assert app.state.knowledge_event_recovery_worker.is_alive()
    release.set()
    app.state.knowledge_event_recovery_worker.join(1)
    assert not app.state.knowledge_event_recovery_worker.is_alive()


def test_recovery_wall_time_is_one_deadline_for_snapshot_lock(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    (events_dir / "inv-lock.jsonl").touch()
    # Prime the schema fast path so this regression measures recovery's
    # receipt/projection deadline rather than DuckDB's cold read-only probe.
    init_database_at_path(graph_db)
    with connect_write(graph_db, purpose="hold_for_deadline"):
        started = time.monotonic()
        with pytest.raises(WriteLockTimeout):
            projector.recover(
                db_path=graph_db,
                events_dir=str(events_dir),
                wall_time_s=0.05,
            )
        elapsed = time.monotonic() - started
    assert elapsed < 0.25


def test_recovery_rotates_past_a_hot_early_investigation(
    graph_db: str, tmp_path: Path
) -> None:
    class Provider:
        def encode(self, _text: str) -> list[float]:
            return [0.0] * 384

    events_dir = tmp_path / "events"
    events_dir.mkdir()
    # Filenames are trajectory authority; make the test events agree with it.
    hot = [_event(f"hot-{index}", "note.emerged", str(index), "2030") for index in range(3)]
    for event in hot:
        event["investigation_id"] = "aaa"
    _write_tail(events_dir / "aaa.jsonl", hot)
    later = _event("later", "note.emerged", "must advance", "2030")
    later["investigation_id"] = "zzz"
    _write_tail(events_dir / "zzz.jsonl", [later])

    projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        candidate_limit=1,
        wall_time_s=5,
        embedding_provider=Provider(),
    )
    projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        candidate_limit=1,
        wall_time_s=5,
        embedding_provider=Provider(),
    )

    with duckdb.connect(graph_db, read_only=True) as con:
        assert con.execute(
            "SELECT next_ordinal FROM event_consumer_frontiers "
            "WHERE investigation_id='zzz'"
        ).fetchone() == (1,)


def test_shutdown_after_embedding_prevents_new_projection_transaction(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-stop", "note.emerged", "do not commit", "2030")],
    )
    stopped = False

    class StopAfterEncode:
        def encode(self, _text: str) -> list[float]:
            nonlocal stopped
            stopped = True
            return [0.0] * 384

    report = projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        wall_time_s=10,
        embedding_provider=StopAfterEncode(),
        should_stop=lambda: stopped,
    )

    assert report.catching_up is True
    con = duckdb.connect(graph_db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM event_consumer_receipts").fetchone()[0] == 0
    finally:
        con.close()


def test_shutdown_before_embedding_never_calls_provider(
    graph_db: str, tmp_path: Path
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_tail(
        events_dir / "inv-1.jsonl",
        [_event("evt-stop-before", "note.emerged", "do not call", "2030")],
    )

    class ForbiddenProvider:
        def encode(self, _text: str) -> list[float]:
            raise AssertionError("provider called after shutdown")

    report = projector.recover(
        db_path=graph_db,
        events_dir=str(events_dir),
        wall_time_s=10,
        embedding_provider=ForbiddenProvider(),
        should_stop=lambda: True,
    )

    assert report.catching_up is True


def test_recovery_missing_schema_never_creates_database(tmp_path: Path) -> None:
    db = str(tmp_path / "missing.duckdb")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    with pytest.raises(projector.SchemaUnavailableError):
        projector.recover(db_path=db, events_dir=str(events_dir), wall_time_s=0.05)
    assert not os.path.exists(db)
