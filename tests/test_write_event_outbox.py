from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.event_log.events import (
    emit_typed,
    investigation_event_lock,
    seal_investigation,
)
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import OutlineBlockRemovedPayload
from substrate.write.event_outbox import (
    EventOutboxError,
    build_typed_envelope,
    dispatch_pending,
    enqueue_event,
    recover_pending_events,
)


@pytest.fixture()
def outbox(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    init_database_at_path(db)
    return db, events


def _event(event_id="evt-fixed", section_id="sec-1"):
    return build_typed_envelope(
        "inv-1",
        OutlineBlockRemovedPayload(outline_block_id="oblk-1", section_id=section_id),
        role="write_composition",
        event_id=event_id,
        emitted_at=datetime(2026, 7, 15, tzinfo=UTC),
    )


def _enqueue(con, event=None):
    event = event or _event()
    return enqueue_event(
        con,
        operation_id="outline.remove:oblk-1",
        aggregate_kind="outline_block",
        aggregate_id="oblk-1",
        event=event,
    )


def test_dispatch_persists_one_exact_event_and_receipt(outbox):
    db, events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        assert dispatch_pending(con, "inv-1", events_dir=str(events)) == ["evt-fixed"]
        row = con.execute(
            "SELECT state, attempt_count FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()
        assert row == ("delivered", 1)
    lines = (events / "inv-1.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_id"] == "evt-fixed"


def test_disabled_events_create_neither_intent_nor_files(outbox, monkeypatch):
    db, events = outbox
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    with connect_write(db, purpose="test/outbox-disabled") as con:
        assert _enqueue(con) == "evt-fixed"
        assert dispatch_pending(con, "inv-1", events_dir=str(events)) == []
        assert con.execute("SELECT COUNT(*) FROM write_event_outbox").fetchone()[0] == 0
    assert not events.exists()


def test_crash_after_fsync_reconciles_without_duplicate(outbox):
    db, events = outbox

    def crash(boundary, _event_id):
        if boundary == "after_append":
            raise RuntimeError("simulated process death")

    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        with pytest.raises(RuntimeError, match="process death"):
            dispatch_pending(con, "inv-1", events_dir=str(events), checkpoint=crash)
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()[0] == "pending"
        assert dispatch_pending(con, "inv-1", events_dir=str(events)) == ["evt-fixed"]
    assert len((events / "inv-1.jsonl").read_text().splitlines()) == 1


def test_identity_reuse_with_changed_bytes_fails(outbox):
    db, _events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        with pytest.raises(EventOutboxError, match="different event bytes"):
            _enqueue(con, _event(section_id="sec-changed"))


def test_malformed_jsonl_retains_pending_intent(outbox):
    db, events = outbox
    events.mkdir()
    (events / "inv-1.jsonl").write_text('{"partial":')
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        with pytest.raises(EventOutboxError, match="malformed line"):
            dispatch_pending(con, "inv-1", events_dir=str(events))
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()[0] == "pending"


def test_new_event_reopens_sealed_stream_as_durable_tail(outbox):
    db, events = outbox
    events.mkdir()
    (events / "inv-1.parquet").write_bytes(b"sealed")
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        assert dispatch_pending(con, "inv-1", events_dir=str(events)) == ["evt-fixed"]
    assert json.loads((events / "inv-1.jsonl").read_text())["event_id"] == "evt-fixed"


def test_partial_v18_schema_is_repaired(outbox):
    db, _events = outbox
    with connect_write(db, purpose="test/drop") as con:
        con.execute("DROP TABLE write_event_outbox")
        con.execute("CREATE TABLE write_event_outbox (event_id TEXT)")
    from substrate.graph import schema

    schema._INITIALIZED_PATHS.discard(db)
    assert schema._schema_is_present(db) is False
    init_database_at_path(db)
    with connect_write(db, purpose="test/read") as con:
        assert con.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='write_event_outbox' AND column_name='operation_id'"
        ).fetchone()[0] == 1


def test_sealing_refuses_pending_write_intent(outbox, monkeypatch):
    db, events = outbox
    events.mkdir()
    (events / "inv-1.jsonl").write_text("")
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    with pytest.raises(RuntimeError, match="pending Write events"):
        seal_investigation("inv-1", events_dir=str(events), outbox_db_path=db)


def test_sealing_cannot_race_past_an_eventful_commit(outbox):
    db, events = outbox
    events.mkdir()
    (events / "inv-1.jsonl").write_text("")
    code = textwrap.dedent(
        f"""
        import time
        from runtime.db_lock import connect_write
        from substrate.schemas.events import OutlineBlockRemovedPayload
        from substrate.write.event_outbox import (
            build_typed_envelope, enqueue_event, eventful_transaction,
        )
        with connect_write({db!r}, purpose='test/racing-writer') as con:
            with eventful_transaction(con, 'inv-1'):
                event = build_typed_envelope(
                    'inv-1',
                    OutlineBlockRemovedPayload(
                        outline_block_id='oblk-race', section_id='sec-race'
                    ),
                    event_id='evt-race',
                )
                enqueue_event(
                    con,
                    operation_id='outline.remove:oblk-race',
                    aggregate_kind='outline_block',
                    aggregate_id='oblk-race',
                    event=event,
                )
                print('ready', flush=True)
                time.sleep(0.3)
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    child = subprocess.Popen(
        [sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="pending Write events"):
            seal_investigation(
                "inv-1", events_dir=str(events), outbox_db_path=db
            )
        assert child.wait(timeout=10) == 0
        assert not (events / "inv-1.parquet").exists()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


def test_investigation_path_traversal_is_rejected(outbox):
    db, events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        event = build_typed_envelope(
            "../escape",
            OutlineBlockRemovedPayload(outline_block_id="oblk-1", section_id="sec-1"),
        )
        enqueue_event(
            con,
            operation_id="unsafe",
            aggregate_kind="outline_block",
            aggregate_id="oblk-1",
            event=event,
        )
        with pytest.raises(ValueError, match="not safe"):
            dispatch_pending(con, "../escape", events_dir=str(events))


def test_populated_partial_v18_schema_fails_closed(outbox):
    db, _events = outbox
    with connect_write(db, purpose="test/partial") as con:
        con.execute("DROP TABLE write_event_outbox")
        con.execute("CREATE TABLE write_event_outbox (event_id TEXT)")
        con.execute("INSERT INTO write_event_outbox VALUES ('evt-unrecoverable')")
    from substrate.graph import schema

    schema._INITIALIZED_PATHS.discard(db)
    with pytest.raises(RuntimeError, match="explicit recovery"):
        init_database_at_path(db)


def test_append_failure_keeps_intent_pending(outbox, monkeypatch):
    db, events = outbox
    import substrate.write.event_outbox as outbox_module

    monkeypatch.setattr(
        outbox_module,
        "_append_durable",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        with pytest.raises(OSError, match="disk full"):
            dispatch_pending(con, "inv-1", events_dir=str(events))
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()[0] == "pending"


def test_symlink_and_hardlink_jsonl_are_rejected(outbox, tmp_path):
    db, events = outbox
    events.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("")
    path = events / "inv-1.jsonl"
    path.symlink_to(outside)
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        with pytest.raises(EventOutboxError, match="singly linked"):
            dispatch_pending(con, "inv-1", events_dir=str(events))
        path.unlink()
        path.hardlink_to(outside)
        with pytest.raises(EventOutboxError, match="singly linked"):
            dispatch_pending(con, "inv-1", events_dir=str(events))


def test_dispatch_preserves_per_investigation_sequence(outbox):
    db, events = outbox
    second = build_typed_envelope(
        "inv-1",
        OutlineBlockRemovedPayload(outline_block_id="oblk-2", section_id="sec-2"),
        event_id="evt-second",
        emitted_at=datetime(2026, 7, 15, 0, 0, 1, tzinfo=UTC),
    )
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
        enqueue_event(
            con,
            operation_id="outline.remove:oblk-2",
            aggregate_kind="outline_block",
            aggregate_id="oblk-2",
            event=second,
        )
        assert dispatch_pending(con, "inv-1", events_dir=str(events)) == [
            "evt-fixed", "evt-second"
        ]
    ids = [
        json.loads(line)["event_id"]
        for line in (events / "inv-1.jsonl").read_text().splitlines()
    ]
    assert ids == ["evt-fixed", "evt-second"]


def _dispatch_subprocess(db, events, *, crash=False):
    code = textwrap.dedent(
        f"""
        import os
        from runtime.db_lock import connect_write
        from substrate.write.event_outbox import dispatch_pending
        def checkpoint(boundary, event_id):
            if {crash!r} and boundary == 'after_append':
                os._exit(73)
        with connect_write({str(db)!r}, purpose='test/outbox-child') as con:
            dispatch_pending(con, 'inv-1', events_dir={str(events)!r}, checkpoint=checkpoint)
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    return subprocess.Popen([sys.executable, "-c", code], env=env)


def test_real_process_death_after_fsync_recovers_exactly_once(outbox):
    db, events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
    child = _dispatch_subprocess(db, events, crash=True)
    assert child.wait(timeout=15) == 73
    assert len((events / "inv-1.jsonl").read_text().splitlines()) == 1
    assert recover_pending_events(db, events_dir=str(events)) == {
        "inv-1": ["evt-fixed"]
    }
    with connect_write(db, purpose="test/outbox-recover") as con:
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()[0] == "delivered"
    assert len((events / "inv-1.jsonl").read_text().splitlines()) == 1


def test_concurrent_process_dispatchers_append_once(outbox):
    db, events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        _enqueue(con)
    children = [_dispatch_subprocess(db, events) for _ in range(2)]
    assert [child.wait(timeout=15) for child in children] == [0, 0]
    assert len((events / "inv-1.jsonl").read_text().splitlines()) == 1
    with connect_write(db, purpose="test/outbox-read") as con:
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE event_id='evt-fixed'"
        ).fetchone()[0] == "delivered"


def test_event_lock_timeout_is_bounded(outbox):
    _db, events = outbox
    code = textwrap.dedent(
        f"""
        import time
        from substrate.event_log.events import investigation_event_lock
        with investigation_event_lock('inv-1', events_dir={str(events)!r}):
            print('ready', flush=True)
            time.sleep(5)
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    child = subprocess.Popen(
        [sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        with (
            pytest.raises(TimeoutError, match="event lock"),
            investigation_event_lock("inv-1", events_dir=str(events), timeout_s=0.05),
        ):
            pass
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_legacy_direct_emit_keeps_nonfatal_contract_for_unsafe_scope(outbox):
    _db, events = outbox
    event_id = emit_typed(
        "../escape",
        OutlineBlockRemovedPayload(outline_block_id="oblk-1", section_id="sec-1"),
        events_dir=str(events),
    )
    assert event_id is not None
    assert not (events.parent / "escape.jsonl").exists()


def test_startup_recovery_drains_multiple_batches(outbox):
    db, events = outbox
    with connect_write(db, purpose="test/outbox") as con:
        for index in range(5):
            event = build_typed_envelope(
                "inv-1",
                OutlineBlockRemovedPayload(
                    outline_block_id=f"oblk-{index}", section_id="sec-1"
                ),
                event_id=f"evt-{index}",
                emitted_at=datetime(2026, 7, 15, 0, 0, index, tzinfo=UTC),
            )
            enqueue_event(
                con,
                operation_id=f"remove-{index}",
                aggregate_kind="outline_block",
                aggregate_id=f"oblk-{index}",
                event=event,
            )
    recovered = recover_pending_events(db, events_dir=str(events), batch_size=2)
    assert recovered == {"inv-1": [f"evt-{index}" for index in range(5)]}
