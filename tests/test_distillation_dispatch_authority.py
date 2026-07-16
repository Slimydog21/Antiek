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
from runtime.research_runner.distillation_execution import (
    ApprovedDistillationTicket,
    DistillationApprovalRequirement,
    DistillationExecutionResult,
    DistillationProviderValue,
    DistillationSpendCorrelation,
)
from runtime.research_runner.provider_gateway import (
    DispatchIneligible,
    PaidFallbackPreparation,
    ProviderOutcomeUnknown,
)
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


def test_authorized_sending_correlation_is_exact_idempotent_and_immutable(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    expected = {
        "spend_run_id": "run-1",
        "fallback_chain_id": "chain-1",
        "manifest_sha256": "a" * 64,
        "fallback_index": 0,
        "hold_id": "hold-1",
    }

    first = journal.authorize_sending("evt-request", **expected)
    assert first.state is CommandState.SENDING
    assert (
        first.spend_run_id,
        first.fallback_chain_id,
        first.manifest_sha256,
        first.fallback_index,
        first.hold_id,
    ) == tuple(expected.values())
    assert journal.authorize_sending("evt-request", **expected) == first

    for field in expected:
        changed = dict(expected)
        changed[field] = (
            "b" * 64
            if field == "manifest_sha256"
            else 2
            if field == "fallback_index"
            else f"changed-{field}"
        )
        with pytest.raises(BindingConflict, match="changed"):
            journal.authorize_sending("evt-request", **changed)
    assert journal.load("evt-request") == first


def test_ambiguous_transition_requires_the_authorized_hold(tmp_path) -> None:
    journal = DistillationDispatchJournal(str(tmp_path / "graph.duckdb"))
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    journal.authorize_sending(
        "evt-request",
        spend_run_id="run-1",
        fallback_chain_id="chain-1",
        manifest_sha256="a" * 64,
        fallback_index=0,
        hold_id="hold-1",
    )

    with pytest.raises(BindingConflict, match="authorized hold"):
        journal.mark_ambiguous("evt-request", hold_id="substituted-hold")
    assert journal.load("evt-request").state is CommandState.SENDING
    assert journal.mark_ambiguous(
        "evt-request", hold_id="hold-1"
    ).state is CommandState.AMBIGUOUS


def test_correlation_conflict_rolls_back_command_transition(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    import duckdb

    with duckdb.connect(db) as connection:
        connection.execute(
            "INSERT INTO distillation_dispatch_hold_correlations "
            "(request_event_id,fallback_index,hold_id,created_at) VALUES (?,?,?,?)",
            ["evt-request", 0, "conflicting-hold", "2026-07-16T00:00:00Z"],
        )

    with pytest.raises(BindingConflict, match="hold identity changed"):
        journal.authorize_sending(
            "evt-request",
            spend_run_id="run-1",
            fallback_chain_id="chain-1",
            manifest_sha256="a" * 64,
            fallback_index=0,
            hold_id="hold-1",
        )
    snapshot = journal.load("evt-request")
    assert snapshot.state is CommandState.RESERVED
    assert snapshot.hold_id is None


def test_fallback_hold_lineage_advances_one_route_and_retains_history(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    base = {
        "spend_run_id": "run-1",
        "fallback_chain_id": "chain-1",
        "manifest_sha256": "a" * 64,
    }
    journal.authorize_sending(
        "evt-request", **base, fallback_index=0, hold_id="hold-0"
    )
    advanced = journal.authorize_sending(
        "evt-request", **base, fallback_index=1, hold_id="hold-1"
    )
    assert (advanced.fallback_index, advanced.hold_id) == (1, "hold-1")
    assert journal.authorize_sending(
        "evt-request", **base, fallback_index=0, hold_id="hold-0"
    ) == advanced
    with pytest.raises(BindingConflict, match="historical hold changed"):
        journal.authorize_sending(
            "evt-request", **base, fallback_index=0, hold_id="substituted-hold"
        )
    with pytest.raises(BindingConflict, match="lineage changed"):
        journal.authorize_sending(
            "evt-request", **base, fallback_index=3, hold_id="hold-3"
        )

    import duckdb

    with duckdb.connect(db) as connection:
        assert connection.execute(
            "SELECT fallback_index,hold_id FROM distillation_dispatch_hold_correlations "
            "WHERE request_event_id='evt-request' ORDER BY fallback_index"
        ).fetchall() == [(0, "hold-0"), (1, "hold-1")]


def test_existing_database_migrates_nullable_correlation_columns(tmp_path) -> None:
    db = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db)
    journal.reserve("evt-request", _binding(), investigation_id="inv-1", document_id=None)
    import duckdb

    with duckdb.connect(db) as connection:
        for column in (
            "spend_run_id",
            "fallback_chain_id",
            "manifest_sha256",
            "fallback_index",
            "hold_id",
        ):
            connection.execute(f"ALTER TABLE distillation_dispatch_commands DROP COLUMN {column}")

    migrated = DistillationDispatchJournal(db).load("evt-request")
    assert migrated.state is CommandState.RESERVED
    assert (
        migrated.spend_run_id,
        migrated.fallback_chain_id,
        migrated.manifest_sha256,
        migrated.fallback_index,
        migrated.hold_id,
    ) == (None, None, None, None, None)


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
    first.join(timeout=30)
    second.join(timeout=30)

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


def _patch_handler_dependencies(
    monkeypatch,
    calls: list[str],
    *,
    crash: bool = False,
    recover_ineligible: bool = False,
):
    monkeypatch.setattr(wrestling, "_resolve_region_text", lambda *args, **kwargs: "source")
    monkeypatch.setattr(wrestling, "build_working_memory_layer", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wrestling,
        "assemble_context_pack",
        lambda **kwargs: SimpleNamespace(text="context", event_id="evt-pack"),
    )

    class Authority:
        prepare_calls = 0

        def prepare(self, request_event_id, prompt):
            self.prepare_calls += 1
            if recover_ineligible and self.prepare_calls > 1:
                raise DispatchIneligible("capability changed")
            return ApprovedDistillationTicket(
                request_event_id=request_event_id,
                prompt=prompt,
                preparation=PaidFallbackPreparation(
                    chain_id="chain",
                    manifest_sha256="a" * 64,
                    ceiling_cents=100,
                    currency="USD",
                    maximum_chain_exposure_cents=100,
                ),
                approval_id="approval",
                run_id="run",
            )

        def execute(self, ticket, authorize_send):
            authorize_send(
                DistillationSpendCorrelation(
                    ticket.run_id,
                    ticket.preparation.chain_id,
                    ticket.preparation.manifest_sha256,
                    0,
                    "hold",
                )
            )
            if crash and calls:
                raise ProviderOutcomeUnknown("hold", "recovered result unavailable")
            calls.append("called")
            if crash:
                raise RuntimeError("process died after transport")
            return DistillationExecutionResult(
                value=DistillationProviderValue(
                    text='{"rendered_text":"answer","claims":[{"text":"claim","confidence":"high"}]}',
                    output_tokens=7,
                ),
                provider="provider",
                model="model",
            )

    authority = Authority()
    original_factory = wrestling.make_distillation_handler

    def factory(*args, **kwargs):
        kwargs.setdefault("execution_authority", authority)
        return original_factory(*args, **kwargs)

    monkeypatch.setattr(wrestling, "make_distillation_handler", factory)
    return authority


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
    assert (
        snapshot.spend_run_id,
        snapshot.fallback_chain_id,
        snapshot.manifest_sha256,
        snapshot.fallback_index,
        snapshot.hold_id,
    ) == ("run", "chain", "a" * 64, 0, "hold")
    delivered = [
        row for row in wrestling.trajectory("inv-1")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0]["policy_id"] == "wrestling-fallback/ambiguous"


@pytest.mark.asyncio
async def test_correlated_recovery_capability_drift_becomes_ambiguous(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    _patch_handler_dependencies(
        monkeypatch, calls, crash=True, recover_ineligible=True
    )
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )
    event = _request_event()

    with pytest.raises(RuntimeError, match="process died"):
        await handler(event)
    await handler(event)

    snapshot = DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        event.event_id
    )
    assert snapshot.state is CommandState.AMBIGUOUS
    assert snapshot.hold_id == "hold"
    assert calls == ["called"]


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
        timeout=30,
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
    db_path = str(tmp_path / "graph.duckdb")
    journal = DistillationDispatchJournal(db_path)
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
    import duckdb

    with duckdb.connect(db_path, read_only=True) as connection:
        persisted = connection.execute(
            "SELECT state,sending_at FROM distillation_dispatch_commands "
            "WHERE request_event_id='evt-request'"
        ).fetchone()
    assert persisted == ("reserved", None)

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
async def test_memory_integrity_fallback_replay_uses_one_durable_delivery(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    calls: list[str] = []
    authority = _patch_handler_dependencies(monkeypatch, calls)

    def corrupt_memory(*args, **kwargs):
        raise PhysicalTrajectoryError("memory evidence conflicts")

    monkeypatch.setattr(wrestling, "build_working_memory_layer", corrupt_memory)
    broadcaster = _Broadcaster()
    handler = wrestling.make_distillation_handler(
        broadcaster,
        db_path=str(tmp_path / "graph.duckdb"),
        execution_authority=authority,
    )

    event = _request_event()
    await handler(event)
    await handler(event)

    assert calls == []
    delivered = [
        row
        for row in wrestling.trajectory("inv-1")
        if row["action_type"] == "distillation.delivered"
    ]
    assert len(delivered) == 1
    assert delivered[0]["policy_id"] == "wrestling-fallback/memory-integrity"
    command = DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        "evt-request"
    )
    assert command.state is CommandState.DELIVERED
    assert command.delivery_event_id == delivered[0]["event_id"]
    assert command.delivery_payload is not None
    assert command.delivery_payload.claims[0].claim_id == "c-memory-" + hashlib.sha256(
        b"evt-request"
    ).hexdigest()[:12]


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


@pytest.mark.asyncio
async def test_unconfigured_paid_route_emits_one_unavailable_state_and_no_delivery(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setattr(wrestling, "_resolve_region_text", lambda *args, **kwargs: "source")
    monkeypatch.setattr(wrestling, "build_working_memory_layer", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wrestling,
        "assemble_context_pack",
        lambda **kwargs: SimpleNamespace(text="context", event_id="evt-pack"),
    )
    event = _request_event()
    handler = wrestling.make_distillation_handler(
        _Broadcaster(), db_path=str(tmp_path / "graph.duckdb")
    )

    await handler(event)
    await handler(event)

    rows = wrestling.trajectory("inv-1")
    required = [
        row for row in rows
        if row["action_type"] == "distillation.approval_required"
    ]
    assert len(required) == 1
    assert required[0]["payload"]["reason"] == "qualified_route_unavailable"
    assert not [row for row in rows if row["action_type"] == "distillation.delivered"]
    assert DistillationDispatchJournal(str(tmp_path / "graph.duckdb")).load(
        event.event_id
    ).state is CommandState.RESERVED


@pytest.mark.asyncio
async def test_prepared_request_waits_reserved_then_executes_after_exact_approval(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setattr(wrestling, "_resolve_region_text", lambda *args, **kwargs: "source")
    monkeypatch.setattr(wrestling, "build_working_memory_layer", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wrestling,
        "assemble_context_pack",
        lambda **kwargs: SimpleNamespace(text="context", event_id="evt-pack"),
    )
    calls: list[str] = []

    class Authority:
        approved = False

        def prepare(self, request_event_id, prompt):
            if not self.approved:
                return DistillationApprovalRequirement(
                    request_event_id=request_event_id,
                    chain_id="chain-1",
                    manifest_sha256="a" * 64,
                    ceiling_cents=100,
                    currency="USD",
                    maximum_chain_exposure_cents=80,
                    reason="approval_required",
                )
            return ApprovedDistillationTicket(
                request_event_id=request_event_id,
                prompt=prompt,
                preparation=PaidFallbackPreparation(
                    "chain-1", "a" * 64, 100, "USD", 80
                ),
                approval_id="approval-1",
                run_id="run-1",
            )

        def execute(self, ticket, authorize_send):
            authorize_send(
                DistillationSpendCorrelation(
                    ticket.run_id,
                    ticket.preparation.chain_id,
                    ticket.preparation.manifest_sha256,
                    0,
                    "hold-1",
                )
            )
            calls.append(ticket.approval_id)
            return DistillationExecutionResult(
                DistillationProviderValue(
                    '{"rendered_text":"answer","claims":[]}', 3
                ),
                "provider",
                "model",
            )

    authority = Authority()
    handler = wrestling.make_distillation_handler(
        _Broadcaster(),
        db_path=str(tmp_path / "graph.duckdb"),
        execution_authority=authority,
    )
    event = _request_event()

    await handler(event)
    await handler(event)
    journal = DistillationDispatchJournal(str(tmp_path / "graph.duckdb"))
    assert journal.load(event.event_id).state is CommandState.RESERVED
    assert calls == []

    authority.approved = True
    await handler(event)
    assert calls == ["approval-1"]
    assert journal.load(event.event_id).state is CommandState.DELIVERED
    rows = wrestling.trajectory("inv-1")
    assert len([r for r in rows if r["action_type"] == "distillation.approval_required"]) == 1
    assert len([r for r in rows if r["action_type"] == "distillation.delivered"]) == 1
