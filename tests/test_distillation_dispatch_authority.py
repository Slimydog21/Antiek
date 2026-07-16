from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import interfaces.research.api.wrestling as wrestling
from substrate.distillation_dispatch import (
    BindingConflict,
    CommandState,
    DistillationDispatchJournal,
    InvalidCommandTransition,
)
from substrate.event_log import PhysicalTrajectoryError, emit_typed
from substrate.schemas import (
    Claim,
    DistillationDeliveredPayload,
    DistillationRequestedPayload,
    Event,
)


class _Broadcaster:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def broadcast(self, event: Event) -> None:
        self.events.append(event)


def _binding(prompt: str = "prompt") -> dict[str, object]:
    return {
        "schema": "test.v1",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "role": "synthesizer",
    }


def _payload(request_event_id: str = "evt-request") -> DistillationDeliveredPayload:
    return DistillationDeliveredPayload(
        request_event_id=request_event_id,
        claims=[Claim(claim_id="c-1", text="claim", confidence="high", attribution_region_ids=[])],
        rendered_text="answer",
        rendered_text_hash="sha256:" + hashlib.sha256(b"answer").hexdigest()[:12],
        token_count=7,
    )


def _request_event(prompt: str = "why?") -> Event:
    return Event(
        event_id="evt-request",
        investigation_id="inv-1",
        role="user",
        action_type="distillation.requested",
        payload=DistillationRequestedPayload(
            user_prompt=prompt, region_id="region-1", target_token_count=256
        ),
        parent_event_id=None,
        policy_id="operator",
        param_version="test",
        schema_version=1,
        emitted_at=datetime.now(UTC),
        document_id="doc-1",
    )


def test_exact_reservation_reopens_and_changed_binding_conflicts(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    first = DistillationDispatchJournal(db)
    snapshot = first.reserve(
        "evt-request", _binding(), investigation_id="inv-1", document_id="doc-1"
    )
    assert snapshot.state is CommandState.RESERVED

    reopened = DistillationDispatchJournal(db)
    assert reopened.reserve(
        "evt-request", _binding(), investigation_id="inv-1", document_id="doc-1"
    ) == snapshot
    with pytest.raises(BindingConflict):
        reopened.reserve(
            "evt-request", _binding("changed"),
            investigation_id="inv-1", document_id="doc-1",
        )


def test_sending_recovery_becomes_permanently_ambiguous(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    journal.mark_sending("evt-request")

    reopened = DistillationDispatchJournal(db)
    assert reopened.load("evt-request").state is CommandState.SENDING
    assert reopened.mark_ambiguous("evt-request").state is CommandState.AMBIGUOUS
    with pytest.raises(InvalidCommandTransition):
        reopened.mark_sending("evt-request")


def test_completed_payload_survives_reopen_before_delivery(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    journal.mark_sending("evt-request")
    completed = journal.mark_completed(
        "evt-request", _payload(), policy_id="provider/model"
    )
    assert completed.state is CommandState.COMPLETED
    assert completed.delivery_payload == _payload()

    reopened = DistillationDispatchJournal(db)
    assert reopened.load("evt-request") == completed
    assert reopened.mark_delivered("evt-request").state is CommandState.DELIVERED


def test_corrupt_completed_payload_fails_closed(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    journal.mark_sending("evt-request")
    journal.mark_completed("evt-request", _payload(), policy_id="provider/model")
    import duckdb

    with duckdb.connect(db) as connection:
        connection.execute(
            "UPDATE distillation_dispatch_commands SET delivery_payload_json=? "
            "WHERE request_event_id='evt-request'",
            [json.dumps({"forged": True})],
        )
    with pytest.raises(RuntimeError, match="digest mismatch"):
        journal.load("evt-request")


def test_concurrent_exact_callers_have_one_transport_winner(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    provider_calls: list[str] = []
    states: list[CommandState] = []

    def invoke() -> None:
        with journal.execution_guard("evt-request"):
            command = journal.reserve(
                "evt-request", _binding(), investigation_id="inv-1", document_id=None
            )
            if command.state is CommandState.RESERVED:
                journal.mark_sending("evt-request")
                provider_calls.append("called")
                time.sleep(0.05)
                journal.mark_completed(
                    "evt-request", _payload(), policy_id="provider/model"
                )
                journal.mark_delivered("evt-request")
            states.append(journal.load("evt-request").state)

    first = threading.Thread(target=invoke)
    second = threading.Thread(target=invoke)
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert provider_calls == ["called"]
    assert states == [CommandState.DELIVERED, CommandState.DELIVERED]


def test_process_death_releases_command_guard_without_clearing_sending(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    code = """
import os, sys, time
from substrate.distillation_dispatch import DistillationDispatchJournal
j = DistillationDispatchJournal(sys.argv[1])
with j.execution_guard('evt-request'):
    j.reserve('evt-request', {'schema': 'test.v1'}, investigation_id='inv-1', document_id=None)
    j.mark_sending('evt-request')
    print('LOCKED', flush=True)
    time.sleep(30)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, db],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "LOCKED"
    child.kill()
    child.wait(timeout=5)

    journal = DistillationDispatchJournal(db)
    with journal.execution_guard("evt-request"):
        assert journal.load("evt-request").state is CommandState.SENDING
        assert journal.mark_ambiguous("evt-request").state is CommandState.AMBIGUOUS


def _patch_handler_dependencies(monkeypatch, calls: list[str], *, crash: bool = False) -> None:
    monkeypatch.setattr(wrestling, "_resolve_region_text", lambda *args, **kwargs: "source")
    monkeypatch.setattr(wrestling, "build_working_memory_layer", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wrestling,
        "assemble_context_pack",
        lambda **kwargs: SimpleNamespace(text="context", event_id="evt-pack"),
    )

    def fake_dispatch(*args, **kwargs):
        calls.append("called")
        if crash:
            raise RuntimeError("process died after transport")
        return SimpleNamespace(
            text='{"rendered_text":"answer","claims":[{"text":"claim","confidence":"high"}]}',
            usage=SimpleNamespace(output_tokens=7),
            provider="provider",
            model="model",
        )

    monkeypatch.setattr(wrestling, "dispatch", fake_dispatch)


@pytest.mark.asyncio
async def test_completed_replay_calls_provider_once_and_emits_one_delivery(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)
    broadcaster = _Broadcaster()
    handler = wrestling.make_distillation_handler(
        broadcaster, db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()

    await handler(event)
    await handler(event)

    assert calls == ["called"]
    rows = wrestling.trajectory("inv-1")
    delivered = [row for row in rows if row["action_type"] == "distillation.delivered"]
    assert len(delivered) == 1
    assert delivered[0]["event_id"].startswith("evt-distill-")
    assert DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        event.event_id
    ).state is CommandState.DELIVERED


@pytest.mark.asyncio
async def test_crash_after_transport_is_ambiguous_and_never_redispatched(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls, crash=True)
    broadcaster = _Broadcaster()
    handler = wrestling.make_distillation_handler(
        broadcaster, db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()

    with pytest.raises(RuntimeError, match="process died"):
        await handler(event)
    await handler(event)

    assert calls == ["called"]
    snapshot = DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        event.event_id
    )
    assert snapshot.state is CommandState.AMBIGUOUS
    delivered = [
        row for row in wrestling.trajectory("inv-1")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0]["policy_id"] == "wrestling-fallback/ambiguous"


@pytest.mark.asyncio
async def test_event_append_before_receipt_reconciles_without_duplicate(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)
    original_mark_delivered = DistillationDispatchJournal.mark_delivered
    failures = 0

    def crash_once(self, request_event_id):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise RuntimeError("crash after event append")
        return original_mark_delivered(self, request_event_id)

    monkeypatch.setattr(DistillationDispatchJournal, "mark_delivered", crash_once)
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()

    with pytest.raises(RuntimeError, match="after event append"):
        await handler(event)
    await handler(event)

    assert calls == ["called"]
    delivered = [
        row for row in wrestling.trajectory("inv-1")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        event.event_id
    ).state is CommandState.DELIVERED


@pytest.mark.asyncio
async def test_changed_request_bytes_never_reuse_or_redispatch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    await handler(_request_event("first"))
    with pytest.raises(BindingConflict):
        await handler(_request_event("changed"))
    assert calls == ["called"]


@pytest.mark.asyncio
async def test_concurrent_async_handlers_do_not_deadlock_or_double_dispatch(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)

    class SlowBroadcaster(_Broadcaster):
        async def broadcast(self, event: Event) -> None:
            await asyncio.sleep(0.05)
            await super().broadcast(event)

    handler = wrestling.make_distillation_handler(
        SlowBroadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()
    await asyncio.wait_for(
        asyncio.gather(handler(event), handler(event)),
        timeout=2,
    )
    assert calls == ["called"]


@pytest.mark.asyncio
async def test_cancelled_waiter_releases_lock_after_blocked_acquire(tmp_path) -> None:
    journal = DistillationDispatchJournal(str(tmp_path / "graph.duckdb"))
    first = journal.execution_guard("evt-request")
    first.__enter__()
    entered = asyncio.Event()

    async def contender() -> None:
        async with journal.async_execution_guard("evt-request"):
            entered.set()

    cancelled = asyncio.create_task(contender())
    await asyncio.sleep(0.05)
    assert not entered.is_set()
    cancelled.cancel()
    await asyncio.to_thread(first.__exit__, None, None, None)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(cancelled, timeout=2)

    await asyncio.wait_for(contender(), timeout=2)
    assert entered.is_set()


def test_proven_unsent_completion_never_uses_sending_state(tmp_path) -> None:
    journal = DistillationDispatchJournal(str(tmp_path / "graph.duckdb"))
    journal.reserve(
        "evt-request",
        {"prompt": "bound"},
        investigation_id="inv-1",
        document_id="doc-1",
    )

    completed = journal.mark_proven_unsent_completed(
        "evt-request",
        _payload(),
        policy_id="wrestling-fallback/memory-integrity",
    )
    assert completed.state is CommandState.COMPLETED

    journal.reserve(
        "evt-sending",
        {"prompt": "bound"},
        investigation_id="inv-1",
        document_id="doc-1",
    )
    journal.mark_sending("evt-sending")
    with pytest.raises(InvalidCommandTransition, match="only reserved"):
        journal.mark_proven_unsent_completed(
            "evt-sending",
            _payload(request_event_id="evt-sending"),
            policy_id="wrestling-fallback/memory-integrity",
        )


@pytest.mark.asyncio
async def test_malformed_completed_event_tail_fails_closed_on_replay(
    tmp_path, monkeypatch
) -> None:
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()
    await handler(event)
    with (events / "inv-1.jsonl").open("ab") as stream:
        stream.write(b"{corrupt}\n")
    with pytest.raises(PhysicalTrajectoryError, match="malformed completed JSONL"):
        await handler(event)
    assert calls == ["called"]


@pytest.mark.asyncio
async def test_preexisting_delivery_identity_refuses_provider_spend(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(monkeypatch, calls)
    event = _request_event()
    journal = DistillationDispatchJournal(str(tmp_path / "graph.duckdb"))
    snapshot = journal.reserve(
        event.event_id,
        wrestling._dispatch_binding(event, "context\n\n" + wrestling.ROLE_PROMPT_TAIL),
        investigation_id=event.investigation_id,
        document_id=event.document_id,
    )
    emit_typed(
        event.investigation_id,
        _payload(event.event_id),
        parent_event_id=event.event_id,
        role="synthesizer",
        document_id=event.document_id,
        policy_id="forged/model",
        event_id=snapshot.delivery_event_id,
        strict_write=True,
    )
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    with pytest.raises(PhysicalTrajectoryError, match="before provider dispatch"):
        await handler(event)
    assert calls == []
