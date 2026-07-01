import argparse
import asyncio
import json

from substrate.event_log import (
    ActionType,
    EventEmitter,
    correlation_context,
    emit_typed,
    log_event,
    trajectory,
)
from substrate.schemas import Event
from substrate.schemas.events import PhaseEnterPayload
from tools.eventlog_query import _rows_for_scope, main as eventlog_query_main, where_did_it_stall


def test_standalone_events_default_to_investigation_id(tmp_path):
    events_dir = str(tmp_path)
    inv = "inv-standalone"

    log_event(inv, ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)
    log_event(inv, ActionType.INVESTIGATION_COMPLETED, events_dir=events_dir)

    rows = trajectory(inv, events_dir=events_dir)
    assert rows
    assert {row["correlation_id"] for row in rows} == {inv}


def test_fanout_parent_correlation_inherits_across_async_and_threadpool(tmp_path):
    events_dir = str(tmp_path)
    parent = "root-X"
    unrelated = "inv-unrelated"
    prebuilt = EventEmitter.create(
        investigation_id="child-prebuilt-emitter",
        events_dir=events_dir,
    )

    async def emit_from_task() -> None:
        log_event("child-create-task", ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    async def emit_from_gather(child_iid: str) -> None:
        log_event(child_iid, ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    def emit_from_threadpool() -> None:
        log_event("child-threadpool", ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    async def run_fanout() -> None:
        with correlation_context(parent):
            log_event("child-direct", "cascade.launched", events_dir=events_dir)
            emit_typed(
                "child-typed",
                PhaseEnterPayload(entered_at="2026-07-01T00:00:00.000000Z"),
                phase=1,
                events_dir=events_dir,
            )
            prebuilt.emit(ActionType.INVESTIGATION_START_REQUESTED)
            await asyncio.create_task(emit_from_task())
            await asyncio.gather(
                emit_from_gather("child-gather-a"),
                emit_from_gather("child-gather-b"),
            )
            await asyncio.to_thread(emit_from_threadpool)

    asyncio.run(run_fanout())
    log_event(unrelated, ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    rows = _rows_for_scope(None, events_dir, parent)
    assert {row["investigation_id"] for row in rows} == {
        "child-direct",
        "child-typed",
        "child-prebuilt-emitter",
        "child-create-task",
        "child-gather-a",
        "child-gather-b",
        "child-threadpool",
    }
    assert {row["correlation_id"] for row in rows} == {parent}
    assert all(row["correlation_id"] != row["investigation_id"] for row in rows)


def test_correlation_context_resets_after_exit(tmp_path):
    events_dir = str(tmp_path)

    with correlation_context("root-X"):
        log_event("child-inside", ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    log_event("child-after", ActionType.INVESTIGATION_START_REQUESTED, events_dir=events_dir)

    inside = trajectory("child-inside", events_dir=events_dir)
    after = trajectory("child-after", events_dir=events_dir)
    assert inside[0]["correlation_id"] == "root-X"
    assert after[0]["correlation_id"] == "child-after"


def test_where_did_it_stall_correlation_reports_per_investigation(tmp_path):
    events_dir = str(tmp_path)
    root = "root-stall"

    log_event(
        "child-a",
        "phase.enter",
        phase=3,
        payload={"action_type": "phase.enter", "note": "child A still open"},
        correlation_id=root,
        events_dir=events_dir,
    )
    log_event(
        "child-b",
        "phase.exit",
        phase=3,
        payload={"action_type": "phase.exit", "latency_ms": 100},
        correlation_id=root,
        events_dir=events_dir,
    )
    log_event(
        "child-b",
        "investigation.completed",
        correlation_id=root,
        events_dir=events_dir,
    )

    rows = where_did_it_stall(
        argparse.Namespace(
            investigation_id=None,
            events_dir=events_dir,
            correlation_id=root,
        )
    )

    by_inv = {row["investigation_id"]: row for row in rows}
    assert by_inv["child-a"]["status"] == "stalled"
    assert by_inv["child-a"]["stalled_phase"] == 3
    assert by_inv["child-a"]["diagnostic"] == "child A still open"
    assert by_inv["child-b"]["status"] == "completed"
    assert by_inv["child-b"]["stalled_phase"] is None


def test_empty_correlation_scope_prints_pre_spr04_hint(tmp_path, capsys):
    inv = "legacy-child"
    row = {
        "event_id": "evt-legacy",
        "investigation_id": inv,
        "synthesis_id": None,
        "phase": 1,
        "role": None,
        "action_type": "dispatch.call",
        "payload": {"provider": "openai", "model": "gpt-test"},
        "parent_event_id": None,
        "policy_id": "orchestrator-deterministic",
        "param_version": "test",
        "schema_version": 28,
        "emitted_at": "2026-07-01T00:00:00.000000Z",
        "document_id": None,
    }
    (tmp_path / f"{inv}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    rc = eventlog_query_main(
        [
            "which-provider-fails",
            "--events-dir",
            str(tmp_path),
            "--correlation-id",
            "root-parent",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == []
    assert "pre-SPR-04 fan-out rows" in captured.err


def test_backward_compat_missing_correlation_id_reads_as_investigation_id(tmp_path):
    inv = "inv-old"
    row = {
        "event_id": "evt-old",
        "investigation_id": inv,
        "synthesis_id": None,
        "phase": 1,
        "role": "phase_log",
        "action_type": "phase.enter",
        "payload": {
            "action_type": "phase.enter",
            "entered_at": "2026-07-01T00:00:00.000000Z",
            "note": None,
            "metadata_json": None,
        },
        "parent_event_id": None,
        "policy_id": "orchestrator-deterministic",
        "param_version": "test",
        "schema_version": 28,
        "emitted_at": "2026-07-01T00:00:00.000000Z",
        "document_id": None,
    }
    (tmp_path / f"{inv}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    rows = trajectory(inv, events_dir=str(tmp_path))
    assert rows[0]["correlation_id"] == inv
    event = Event.model_validate(rows[0])
    assert event.correlation_id == inv
