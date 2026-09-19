from __future__ import annotations

import asyncio
import contextlib
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from interfaces.research.api.broadcast import EventBroadcaster
from orchestration.loop_one.coordinator import InvestigationCoordinator, broadcast_emit
from orchestration.loop_one.orchestrator import (
    InvestigationContext,
    _maybe_export_research_artifact_after_complete,
    make_loop_one_handler,
)
from substrate.dispatch.research_quote import build_research_route_manifest
from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing
from substrate.event_log import (
    IdempotencyConflict,
    InvestigationExecutionBusy,
    InvestigationExecutionInvalid,
    append_event_once_authorized,
    assert_investigation_execution_authorized,
    claim_investigation_execution_authorized,
    complete_investigation_execution_authorized,
    emit_typed,
    investigation_execution_context,
    investigation_execution_mutation,
    prepare_typed_event,
    renew_investigation_execution_authorized,
    trajectory_authorized,
    trajectory_authorized_append_order,
)
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import (
    DecomposeQuestionRequestedPayload,
    InvestigationExecutionTakenOverPayload,
    InvestigationFailedPayload,
    InvestigationStartRequestedPayload,
    PhaseEnterPayload,
    ResearchQuotedRoute,
)


def _manifest():
    pricing = TierPricing(
        input_per_mtok=1.0,
        output_per_mtok=2.0,
        cached_input_per_mtok=0.1,
        currency="USD",
        billing_unit="per_million_tokens",
        source_url="https://provider.example/pricing",
        verified_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )
    route = TierConfig("pro", "provider", "model", 100, 0.2, 1000, pricing)
    return build_research_route_manifest(
        DispatchConfig(role_tiers={"decomposer": "pro"}, tiers={"pro": route})
    )


def _authority(tmp_path: Path, account: str = "alice"):
    authority = InvestigationAuthority(account, "inv-execution", tmp_path)
    initialize_composite_stream(authority)
    manifest = _manifest()
    start = prepare_typed_event(
        authority.investigation_id,
        InvestigationStartRequestedPayload(
            question="Recover this investigation",
            approved_run_ceiling_usd=1.0,
            research_quote_id="a" * 64,
            research_quote_payload_sha256="b" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
        ),
        event_id="evt-execution-start",
    )
    append_event_once_authorized(authority, start)
    return authority, start


def test_claim_replay_renew_takeover_and_stale_generation_fence(tmp_path):
    authority, _ = _authority(tmp_path)
    holder_a = "1" * 64
    holder_b = "2" * 64
    claim, first, acquired = claim_investigation_execution_authorized(
        authority, holder_digest=holder_a, now_ms=100_000, ttl_ms=10_000
    )
    assert claim is not None and acquired and first.generation == 1
    replay, replay_snapshot, replay_acquired = claim_investigation_execution_authorized(
        authority, holder_digest=holder_a, now_ms=101_000, ttl_ms=10_000
    )
    assert replay is not None and replay.event_id == claim.event_id
    assert replay_snapshot == first and replay_acquired
    with pytest.raises(InvestigationExecutionBusy):
        claim_investigation_execution_authorized(
            authority, holder_digest=holder_b, now_ms=105_000, ttl_ms=10_000
        )

    renewal, renewed = renew_investigation_execution_authorized(
        authority,
        generation=1,
        holder_digest=holder_a,
        now_ms=105_000,
        ttl_ms=10_000,
    )
    assert renewal.parent_event_id == claim.event_id
    assert renewed.expires_at_ms == 115_000
    with pytest.raises(InvestigationExecutionBusy):
        claim_investigation_execution_authorized(
            authority,
            holder_digest=holder_b,
            now_ms=119_999,
            ttl_ms=10_000,
            clock_skew_margin_ms=5_000,
        )
    takeover, second, acquired = claim_investigation_execution_authorized(
        authority,
        holder_digest=holder_b,
        now_ms=120_000,
        ttl_ms=10_000,
        clock_skew_margin_ms=5_000,
    )
    assert takeover is not None and acquired and second.generation == 2
    assert takeover.parent_event_id == renewal.event_id
    with pytest.raises(InvestigationExecutionBusy, match="stale"):
        assert_investigation_execution_authorized(
            authority, generation=1, holder_digest=holder_a, now_ms=120_001
        )
    assert (
        assert_investigation_execution_authorized(
            authority, generation=2, holder_digest=holder_b, now_ms=120_001
        ).lease_event_id
        == takeover.event_id
    )


def test_completion_binds_persisted_generation_terminal_and_replays(tmp_path):
    authority, _ = _authority(tmp_path)
    holder = "1" * 64
    _, lease, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100_000, ttl_ms=10_000
    )
    terminal = prepare_typed_event(
        authority.investigation_id,
        InvestigationFailedPayload(phase=1, reason="fixture terminal"),
        event_id="evt-execution-terminal",
        execution_generation=lease.generation,
    )
    append_event_once_authorized(authority, terminal)
    completion, completed = complete_investigation_execution_authorized(
        authority,
        generation=lease.generation,
        holder_digest=holder,
        terminal_event=terminal,
        completed_at_ms=101_000,
    )
    replay, replay_snapshot = complete_investigation_execution_authorized(
        authority,
        generation=lease.generation,
        holder_digest=holder,
        terminal_event=terminal,
        completed_at_ms=102_000,
    )
    assert replay.event_id == completion.event_id
    assert replay_snapshot == completed and completed.completed
    _, terminal_truth, acquired = claim_investigation_execution_authorized(
        authority, holder_digest="2" * 64, now_ms=200_000, ttl_ms=10_000
    )
    assert not acquired and terminal_truth.terminal_event_id == terminal.event_id
    with pytest.raises(IdempotencyConflict):
        complete_investigation_execution_authorized(
            authority,
            generation=lease.generation,
            holder_digest=holder,
            terminal_event=terminal.model_copy(update={"event_id": "evt-other"}),
            completed_at_ms=103_000,
        )


def test_completion_rejects_unpersisted_or_ungenerated_terminal(tmp_path):
    authority, _ = _authority(tmp_path)
    holder = "1" * 64
    _, lease, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100_000, ttl_ms=10_000
    )
    terminal = prepare_typed_event(
        authority.investigation_id,
        InvestigationFailedPayload(phase=1, reason="not authorized"),
        event_id="evt-unpersisted-terminal",
    )
    with pytest.raises(InvestigationExecutionInvalid, match="not authorized"):
        complete_investigation_execution_authorized(
            authority,
            generation=lease.generation,
            holder_digest=holder,
            terminal_event=terminal,
            completed_at_ms=101_000,
        )


def test_malformed_early_takeover_and_cross_account_access_fail(tmp_path):
    authority, _ = _authority(tmp_path)
    holder = "1" * 64
    claim, lease, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100_000, ttl_ms=10_000
    )
    assert claim is not None
    forged = prepare_typed_event(
        authority.investigation_id,
        InvestigationExecutionTakenOverPayload(
            execution_id=lease.execution_id,
            prior_receipt_event_id=claim.event_id,
            prior_generation=1,
            generation=2,
            prior_holder_digest=holder,
            holder_digest="2" * 64,
            prior_expires_at_ms=110_000,
            clock_skew_margin_ms=5_000,
            taken_over_at_ms=110_001,
            expires_at_ms=120_001,
        ),
        execution_generation=2,
    )
    append_event_once_authorized(authority, forged)
    with pytest.raises(InvestigationExecutionInvalid, match="takeover conflicts"):
        claim_investigation_execution_authorized(
            authority, holder_digest="3" * 64, now_ms=200_000, ttl_ms=10_000
        )
    foreign = InvestigationAuthority("bob", authority.investigation_id, tmp_path)
    with pytest.raises((RuntimeError, ValueError)):
        claim_investigation_execution_authorized(
            foreign, holder_digest="4" * 64, now_ms=200_000, ttl_ms=10_000
        )


def test_two_processes_race_to_one_generation_one_holder(tmp_path):
    authority, _ = _authority(tmp_path)
    script = """
import pathlib, sys, time
from substrate.event_log import InvestigationExecutionBusy, claim_investigation_execution_authorized
from substrate.investigation_tenancy import InvestigationAuthority
root, marker, peer, holder = sys.argv[1:]
pathlib.Path(marker).touch()
deadline = time.monotonic() + 10
while not pathlib.Path(peer).exists():
    if time.monotonic() > deadline: raise RuntimeError('barrier timeout')
    time.sleep(0.01)
authority = InvestigationAuthority('alice', 'inv-execution', pathlib.Path(root))
try:
    _, snapshot, acquired = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100000, ttl_ms=10000
    )
    print(f'acquired:{snapshot.generation}:{acquired}')
except InvestigationExecutionBusy:
    print('busy')
"""
    markers = [tmp_path / "lease-ready-1", tmp_path / "lease-ready-2"]
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path),
                str(markers[index]),
                str(markers[1 - index]),
                str(index + 1) * 64,
            ],
            cwd=Path(__file__).parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(2)
    ]
    outcomes = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        outcomes.append(stdout.strip())
    assert outcomes.count("busy") == 1
    assert sum(outcome.startswith("acquired:1:True") for outcome in outcomes) == 1
    rows = trajectory_authorized_append_order(authority)
    assert sum(
        row["action_type"] == "investigation.execution_claimed" for row in rows
    ) == 1


def test_execution_context_stamps_generation_and_stale_writer_fails(tmp_path):
    authority, _ = _authority(tmp_path)
    holder_a = "a" * 64
    holder_b = "b" * 64
    now_ms = time.time_ns() // 1_000_000
    _, first, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder_a, now_ms=now_ms, ttl_ms=10_000
    )
    with investigation_execution_context(
        authority, generation=first.generation, holder_digest=holder_a
    ):
        event_id = emit_typed(
            authority.investigation_id,
            PhaseEnterPayload(entered_at="2026-01-01T00:00:00Z"),
            phase=1,
        )
    stamped = next(
        row for row in trajectory_authorized(authority) if row["event_id"] == event_id
    )
    assert stamped["execution_generation"] == 1

    claim_investigation_execution_authorized(
        authority,
        holder_digest=holder_b,
        now_ms=now_ms + 15_000,
        ttl_ms=10_000,
        clock_skew_margin_ms=5_000,
    )
    with (
        investigation_execution_context(
            authority, generation=first.generation, holder_digest=holder_a
        ),
        pytest.raises(InvestigationExecutionBusy, match="stale"),
    ):
        emit_typed(
            authority.investigation_id,
            PhaseEnterPayload(entered_at="2026-01-01T00:00:01Z"),
            phase=2,
        )
    assert sum(
        row["action_type"] == "phase.enter"
        for row in trajectory_authorized(authority)
    ) == 1


def test_takeover_waits_for_atomic_artifact_mutation(tmp_path):
    authority, _ = _authority(tmp_path)
    holder_a = "7" * 64
    holder_b = "8" * 64
    now_ms = time.time_ns() // 1_000_000
    _, first, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder_a, now_ms=now_ms, ttl_ms=10_000
    )
    entered = threading.Event()
    release = threading.Event()
    takeover_done = threading.Event()

    def mutate():
        with (
            investigation_execution_context(
                authority, generation=first.generation, holder_digest=holder_a
            ),
            investigation_execution_mutation(authority),
        ):
            entered.set()
            assert release.wait(5)

    def takeover():
        claim_investigation_execution_authorized(
            authority,
            holder_digest=holder_b,
            now_ms=now_ms + 15_000,
            ttl_ms=10_000,
            clock_skew_margin_ms=5_000,
        )
        takeover_done.set()

    mutation_thread = threading.Thread(target=mutate)
    takeover_thread = threading.Thread(target=takeover)
    mutation_thread.start()
    assert entered.wait(5)
    takeover_thread.start()
    assert not takeover_done.wait(0.1)
    release.set()
    mutation_thread.join(5)
    takeover_thread.join(5)
    assert takeover_done.is_set()


def test_paid_projection_error_propagates_before_terminal(tmp_path, monkeypatch):
    authority, _ = _authority(tmp_path)
    ctx = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
        execution_id="execution-present",
    )
    monkeypatch.setenv("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "1")
    monkeypatch.setattr(
        "substrate.research_artifact.hooks.maybe_export_after_investigation_complete",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("export failed")),
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator.investigation_execution_mutation",
        lambda _authority: contextlib.nullcontext(),
    )
    with pytest.raises(RuntimeError, match="export failed"):
        _maybe_export_research_artifact_after_complete(ctx)


def test_deterministic_command_replays_across_takeover_without_second_append(tmp_path):
    authority, _ = _authority(tmp_path)
    now_ms = time.time_ns() // 1_000_000
    _, first, _ = claim_investigation_execution_authorized(
        authority, holder_digest="9" * 64, now_ms=now_ms, ttl_ms=10_000
    )
    command_id = "evt-loop-command-test"
    payload = DecomposeQuestionRequestedPayload(question="Q", context="")
    with investigation_execution_context(
        authority, generation=1, holder_digest="9" * 64
    ):
        assert emit_typed(
            authority.investigation_id, payload, event_id=command_id, phase=1
        ) == command_id
    _, second, _ = claim_investigation_execution_authorized(
        authority,
        holder_digest="f" * 64,
        now_ms=now_ms + 15_000,
        ttl_ms=10_000,
        clock_skew_margin_ms=5_000,
    )
    with investigation_execution_context(
        authority, generation=second.generation, holder_digest="f" * 64
    ):
        assert emit_typed(
            authority.investigation_id, payload, event_id=command_id, phase=1
        ) == command_id
    commands = [
        row for row in trajectory_authorized(authority) if row["event_id"] == command_id
    ]
    assert len(commands) == 1
    assert commands[0]["execution_generation"] == first.generation


def test_claim_seals_terminal_left_by_crash_without_takeover(tmp_path):
    authority, _ = _authority(tmp_path)
    holder = "c" * 64
    _, snapshot, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100_000, ttl_ms=10_000
    )
    terminal = prepare_typed_event(
        authority.investigation_id,
        InvestigationFailedPayload(
            phase=3, reason="durable failure", last_completed_phase=2
        ),
        execution_generation=snapshot.generation,
    )
    append_event_once_authorized(authority, terminal)

    receipt, recovered, acquired = claim_investigation_execution_authorized(
        authority,
        holder_digest="d" * 64,
        now_ms=200_000,
        ttl_ms=10_000,
    )
    assert receipt is None and not acquired and recovered.completed
    assert recovered.terminal_event_id == terminal.event_id
    assert recovered.generation == 1
    assert sum(
        row["action_type"] == "investigation.execution_completed"
        for row in trajectory_authorized(authority)
    ) == 1


@pytest.mark.asyncio
async def test_paid_handler_claims_completes_and_duplicate_start_is_noop(
    tmp_path, monkeypatch
):
    authority, start = _authority(tmp_path)
    broadcaster = EventBroadcaster()
    coordinator = InvestigationCoordinator(broadcaster)
    handler = make_loop_one_handler(
        broadcaster, coordinator, tenancy_root=tmp_path
    )
    broadcaster.bind_event_authority(start.event_id, authority)

    calls = 0

    async def fake_run(ctx, bus, _coordinator):
        nonlocal calls
        calls += 1
        ctx.failed_phase = 1
        ctx.fail_reason = "deterministic fixture stop"
        ctx.terminal_event_id = await broadcast_emit(
            bus,
            ctx.investigation_id,
            InvestigationFailedPayload(
                phase=1,
                reason=ctx.fail_reason,
                last_completed_phase=None,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
        )

    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._run_investigation", fake_run
    )
    await handler(start)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = trajectory_authorized(authority)
        if any(
            row["action_type"] == "investigation.execution_completed"
            for row in rows
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("handler did not seal its terminal event")

    await handler(start)
    await asyncio.sleep(0.05)
    rows = trajectory_authorized(authority)
    assert calls == 1
    assert sum(
        row["action_type"] == "investigation.execution_claimed" for row in rows
    ) == 1
    assert sum(row["action_type"] == "investigation.failed" for row in rows) == 1
    assert sum(
        row["action_type"] == "investigation.execution_completed" for row in rows
    ) == 1


@pytest.mark.asyncio
async def test_takeover_resumes_request_under_new_generation(
    tmp_path, monkeypatch
):
    authority, start = _authority(tmp_path)
    holder = "e" * 64
    _, first, _ = claim_investigation_execution_authorized(
        authority, holder_digest=holder, now_ms=100_000, ttl_ms=10_000
    )
    request = prepare_typed_event(
        authority.investigation_id,
        DecomposeQuestionRequestedPayload(question="Q", context=""),
        execution_generation=first.generation,
    )
    append_event_once_authorized(authority, request)

    resumed = 0

    async def resume_with_terminal(ctx, bus, _coordinator):
        nonlocal resumed
        resumed += 1
        await broadcast_emit(
            bus,
            ctx.investigation_id,
            InvestigationFailedPayload(
                phase=1,
                reason="fixture resumed",
                last_completed_phase=None,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
        )

    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._run_investigation",
        resume_with_terminal,
    )
    broadcaster = EventBroadcaster()
    handler = make_loop_one_handler(
        broadcaster, InvestigationCoordinator(broadcaster), tenancy_root=tmp_path
    )
    broadcaster.bind_event_authority(start.event_id, authority)
    await handler(start)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = trajectory_authorized(authority)
        if any(
            row["action_type"] == "investigation.execution_completed"
            for row in rows
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("resumed terminal was not sealed")
    failed = [row for row in rows if row["action_type"] == "investigation.failed"]
    assert len(failed) == 1
    assert resumed == 1
    assert failed[0]["payload"]["reason"] == "fixture resumed"
    assert failed[0]["execution_generation"] == 2
    assert sum(
        row["action_type"] == "investigation.execution_taken_over" for row in rows
    ) == 1
