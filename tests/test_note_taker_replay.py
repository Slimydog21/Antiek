from __future__ import annotations

import json
import multiprocessing
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
                claim_id=f"claim-{index}", claim_text=f"Claim {index}",
                located_region_id=f"region-{index}", confidence=0.95,
            ),
            document_id="doc-1", events_dir=str(events_dir), role="grounder",
        )


def _response(request, idempotency_key=None):
    return json.dumps({"notes": [{
        "text": "A durable insight.", "confidence": "high",
        "source_event_ids": request["source_event_ids"],
    }]})


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
    notes = [row for row in iter_physical_events("inv-1", events_dir=str(events))
             if row["action_type"] == "note.emerged"]
    assert len(notes) == 1
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM note_taker_windows").fetchone()[0] == "completed"


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


def test_replay_does_not_deliver_unrelated_outbox_rows(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(db)
    _qualifying(events, 5)
    unrelated = build_typed_envelope(
        "inv-1", NoteEmergedPayload(note_id="other", note_text="Unrelated",
        source_event_ids=["source"], confidence="high", node_id=None),
        document_id="doc-1",
    )
    with connect_write(db, purpose="test/unrelated-outbox") as con:
        enqueue_event(con, operation_id="other:1", aggregate_kind="other",
                      aggregate_id="other-1", event=unrelated)
    delivered = DurableNoteTakerReplay(_response, db_path=db, events_dir=str(events)).catch_up("inv-1")
    assert unrelated.event_id not in delivered
    with connect_read(db) as con:
        assert con.execute("SELECT state FROM write_event_outbox WHERE event_id=?", [unrelated.event_id]).fetchone() == ("pending",)


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
        DurableNoteTakerReplay(LocallyInvalid(), db_path=db, events_dir=str(events)).catch_up("inv-1")
    with connect_read(db) as con:
        assert con.execute("SELECT state, attempt_count FROM note_taker_windows").fetchone() == ("prepared", 0)


def test_v20_fingerprint_rejects_wrong_defaults_constraints_and_index(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    from substrate.graph.schema import _v20_note_taker_shape_is_valid
    with connect_write(db, purpose="test/v20-strict") as con:
        assert _v20_note_taker_shape_is_valid(con)
        con.execute("DROP INDEX idx_note_taker_windows_recovery")
        assert not _v20_note_taker_shape_is_valid(con)


def test_startup_recovery_enumerates_physical_streams_on_daemon(tmp_path, monkeypatch):
    from interfaces.research.api import note_taking
    from substrate.graph import knowledge_event_projector

    seen = []
    monkeypatch.setattr(knowledge_event_projector, "discover_investigations", lambda root: ["inv-a", "inv-b"])
    monkeypatch.setattr(DurableNoteTakerReplay, "catch_up", lambda self, iid: seen.append(iid) or [])
    thread = note_taking.start_replay_recovery(
        db_path=str(tmp_path / "graph.duckdb"), events_dir=str(tmp_path / "events")
    )
    assert thread.daemon
    thread.join(5)
    assert seen == ["inv-a", "inv-b"]
