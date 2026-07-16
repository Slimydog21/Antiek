from __future__ import annotations

import json
import multiprocessing
import threading
import time

import pytest

from roles.note_taker.replay import DurableNoteTakerReplay, NoteTakerReplayCorruption
from runtime.db_lock import connect_read, connect_write
from substrate.event_log import emit_typed, iter_physical_events
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ClaimGroundingCheckPassedPayload, NoteEmergedPayload
from substrate.write.event_outbox import build_typed_envelope, enqueue_event


def _crashing_owner(db: str, events: str, entered: str) -> None:
    def dispatch_forever(request, idempotency_key=None):
        del request, idempotency_key
        open(entered, "w").close()
        while True:
            time.sleep(1)

    DurableNoteTakerReplay(dispatch_forever, db_path=db, events_dir=events).catch_up("inv-1")


def _recovering_owner(db: str, events: str, done: str) -> None:
    DurableNoteTakerReplay(_response, db_path=db, events_dir=events).catch_up("inv-1")
    open(done, "w").close()


def _qualifying(events_dir, count: int, *, start: int = 0) -> None:
    for index in range(start, start + count):
        emit_typed(
            "inv-1",
            ClaimGroundingCheckPassedPayload(
                claim_id=f"claim-{index}",
                claim_text=f"Claim {index}",
                located_region_id=f"region-{index}",
                confidence=0.95,
            ),
            document_id="doc-1",
            events_dir=str(events_dir),
            role="grounder",
        )


def _response(request, idempotency_key=None):
    return json.dumps(
        {
            "notes": [
                {
                    "text": "A durable insight.",
                    "confidence": "high",
                    "source_event_ids": request["source_event_ids"],
                }
            ]
        }
    )


def test_historical_discovery_releases_writer_lock_between_windows(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 10)
    observed: list[str] = []

    def checkpoint(name: str, window_id: str) -> None:
        if name != "prepared":
            return
        with connect_write(
            db, purpose="test/interleaved_deploy_verifier", timeout_s=0.2
        ) as con:
            assert con.execute("SELECT 1").fetchone() == (1,)
        observed.append(window_id)

    DurableNoteTakerReplay(
        _response,
        db_path=db,
        events_dir=str(events),
        checkpoint=checkpoint,
    ).catch_up("inv-1")
    assert len(observed) == 2


def test_restart_combines_events_into_one_deterministic_window(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    calls = []

    def dispatcher(request, idempotency_key=None):
        calls.append(idempotency_key)
        return _response(request)

    _qualifying(events, 3)
    DurableNoteTakerReplay(dispatcher, db_path=db, events_dir=str(events)).catch_up("inv-1")
    assert calls == []
    _qualifying(events, 2, start=3)
    DurableNoteTakerReplay(dispatcher, db_path=db, events_dir=str(events)).catch_up("inv-1")
    DurableNoteTakerReplay(dispatcher, db_path=db, events_dir=str(events)).catch_up("inv-1")
    assert len(calls) == 1
    notes = [
        row
        for row in iter_physical_events("inv-1", events_dir=str(events))
        if row["action_type"] == "note.emerged"
    ]
    assert len(notes) == 1
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "completed"


def test_identical_physical_duplicate_does_not_shift_windows(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)
    path = events / "inv-1.jsonl"
    first = path.read_text().splitlines()[0]
    with path.open("a") as stream:
        stream.write(first + "\n")
    calls = []

    def dispatcher(request, idempotency_key=None):
        calls.append(request["source_event_ids"])
        return _response(request)

    DurableNoteTakerReplay(dispatcher, db_path=db, events_dir=str(events)).catch_up("inv-1")
    assert len(calls) == 1
    assert len(calls[0]) == 5


def test_conflicting_physical_duplicate_fails_closed(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)
    path = events / "inv-1.jsonl"
    conflicting = json.loads(path.read_text().splitlines()[0])
    conflicting["payload"]["claim_text"] = "conflicting bytes"
    with path.open("a") as stream:
        stream.write(json.dumps(conflicting) + "\n")
    with pytest.raises(NoteTakerReplayCorruption, match="identity conflicts"):
        DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up("inv-1")


def test_provider_failure_is_uncertain_and_never_retried(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)
    calls = 0

    def ambiguous(request, idempotency_key=None):
        nonlocal calls
        calls += 1
        raise TimeoutError("outcome unknown")

    service = DurableNoteTakerReplay(ambiguous, db_path=db, events_dir=str(events))
    with pytest.raises(TimeoutError):
        service.catch_up("inv-1")
    service.catch_up("inv-1")
    assert calls == 1
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "uncertain"


def test_threshold_drift_fails_before_reprocessing_history(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)
    calls = 0

    def dispatcher(request, idempotency_key=None):
        nonlocal calls
        calls += 1
        return _response(request)

    DurableNoteTakerReplay(
        dispatcher, db_path=db, events_dir=str(events), threshold=5
    ).catch_up("inv-1")
    with pytest.raises(NoteTakerReplayCorruption, match="configuration drift"):
        DurableNoteTakerReplay(
            dispatcher, db_path=db, events_dir=str(events), threshold=10
        ).catch_up("inv-1")
    assert calls == 1
    with connect_read(db) as con:
        assert con.execute("SELECT COUNT(*) FROM note_taker_windows").fetchone()[0] == 1


def test_incomplete_tail_fails_before_state_advances(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    (events / "inv-1.jsonl").write_bytes(b'{"event_id":"partial"}')
    with pytest.raises(NoteTakerReplayCorruption, match="incomplete"):
        DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up("inv-1")
    with connect_read(db) as con:
        assert con.execute("SELECT COUNT(*) FROM note_taker_windows").fetchone()[0] == 0


def test_empty_partial_v20_is_repaired_but_populated_partial_fails(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database

    with connect_write(db, purpose="test/v20-shape") as con:
        con.execute("DROP TABLE note_taker_windows")
        con.execute("CREATE TABLE note_taker_windows (window_id TEXT)")
        init_database(con)
        con.execute("DROP TABLE note_taker_windows")
        con.execute("CREATE TABLE note_taker_windows (window_id TEXT)")
        con.execute("INSERT INTO note_taker_windows VALUES ('occupied')")
        with pytest.raises(RuntimeError, match="populated partial V20"):
            init_database(con)


def test_cross_process_owner_cannot_be_recovered_until_it_dies(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)
    entered, done = str(tmp_path / "entered"), str(tmp_path / "done")
    context = multiprocessing.get_context("fork")
    owner = context.Process(target=_crashing_owner, args=(db, str(events), entered))
    owner.start()
    deadline = time.monotonic() + 5
    while not tmp_path.joinpath("entered").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert tmp_path.joinpath("entered").exists()
    contender = context.Process(target=_recovering_owner, args=(db, str(events), done))
    contender.start()
    time.sleep(0.2)
    assert contender.is_alive()
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "calling"
    owner.terminate()
    owner.join(5)
    contender.join(5)
    assert contender.exitcode == 0 and tmp_path.joinpath("done").exists()
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "uncertain"


def test_replay_drains_older_unrelated_rows_without_broadcasting_them(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    _qualifying(events, 5)
    unrelated = build_typed_envelope(
        "inv-1",
        NoteEmergedPayload(
            note_id="other",
            note_text="Unrelated",
            source_event_ids=["source"],
            confidence="high",
            node_id=None,
        ),
        document_id="doc-1",
    )
    with connect_write(db, purpose="test/unrelated-outbox") as con:
        enqueue_event(
            con,
            operation_id="other:1",
            aggregate_kind="other",
            aggregate_id="other-1",
            event=unrelated,
        )
    delivered = DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up(
        "inv-1"
    )
    assert unrelated.event_id not in delivered
    with connect_read(db) as con:
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id=?", [unrelated.event_id]
        ).fetchone() == ("delivered",)
    physical_ids = [
        row["event_id"]
        for row in iter_physical_events("inv-1", events_dir=str(events))
    ]
    assert physical_ids.index(unrelated.event_id) < physical_ids.index(delivered[0])


def test_local_pre_dispatch_validation_leaves_window_prepared(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _qualifying(events, 5)

    class LocallyInvalid:
        __signature__ = "not-a-signature"

        def __call__(self, request):  # pragma: no cover - must not be entered
            raise AssertionError(request)

    with pytest.raises(TypeError):
        DurableNoteTakerReplay(LocallyInvalid(), db_path=db, events_dir=str(events)).catch_up(
            "inv-1"
        )
    with connect_read(db) as con:
        assert con.execute("SELECT state, attempt_count FROM note_taker_windows").fetchone() == (
            "prepared",
            0,
        )


def test_v20_fingerprint_rejects_wrong_defaults_constraints_and_index(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    from substrate.graph.schema import _v20_note_taker_shape_is_valid

    with connect_write(db, purpose="test/v20-strict") as con:
        assert _v20_note_taker_shape_is_valid(con)
        con.execute(
            "ALTER TABLE note_taker_windows ALTER COLUMN attempt_count "
            "DROP DEFAULT"
        )
        assert not _v20_note_taker_shape_is_valid(con)


def test_v20_configuration_fingerprint_rejects_wrong_default(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    from substrate.graph.schema import _v20_configuration_shape_is_valid

    with connect_write(db, purpose="test/v20-config-strict") as con:
        assert _v20_configuration_shape_is_valid(con)
        con.execute(
            "ALTER TABLE note_taker_configurations ALTER COLUMN created_at "
            "DROP DEFAULT"
        )
        assert not _v20_configuration_shape_is_valid(con)


def test_v20_fingerprint_rejects_missing_index(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    from substrate.graph.schema import _v20_note_taker_shape_is_valid

    with connect_write(db, purpose="test/v20-index-strict") as con:
        assert _v20_note_taker_shape_is_valid(con)
        con.execute("DROP INDEX idx_note_taker_windows_recovery")
        assert not _v20_note_taker_shape_is_valid(con)


def test_startup_recovery_enumerates_physical_streams_on_daemon(tmp_path, monkeypatch):
    from interfaces.research.api import note_taking
    from substrate.graph import knowledge_event_projector

    seen = []
    monkeypatch.setattr(
        knowledge_event_projector, "discover_investigations", lambda root: ["inv-a", "inv-b"]
    )
    stop = threading.Event()

    def catch_up(_self, investigation_id):
        seen.append(investigation_id)
        if investigation_id == "inv-b":
            stop.set()
        return []

    monkeypatch.setattr(DurableNoteTakerReplay, "catch_up", catch_up)
    thread = note_taking.start_replay_recovery(
        db_path=str(tmp_path / "graph.duckdb"),
        events_dir=str(tmp_path / "events"),
        stop_event=stop,
        poll_interval_s=0.01,
    )
    assert thread.daemon
    deadline = time.monotonic() + 5
    while seen != ["inv-a", "inv-b"] and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(5)
    assert seen == ["inv-a", "inv-b"]


def test_zero_window_recovery_never_opens_replay_writer(tmp_path, monkeypatch):
    from roles.note_taker import replay

    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    service = DurableNoteTakerReplay(
        _response,
        db_path=db,
        events_dir=str(events),
    )
    purposes = []
    original = replay.connect_write

    def observed_connect(db_path, *, purpose, **kwargs):
        purposes.append(purpose)
        return original(db_path, purpose=purpose, **kwargs)

    monkeypatch.setattr(replay, "connect_write", observed_connect)
    assert service.catch_up("inv-a") == []
    assert purposes == []
    with connect_read(db) as con:
        assert con.execute("SELECT COUNT(*) FROM note_taker_configurations").fetchone() == (0,)
