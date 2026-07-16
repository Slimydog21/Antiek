from __future__ import annotations

import gc
import hashlib
import json
import multiprocessing
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from runtime.provider_broker import (
    BrokerDispatchIntent,
    BrokerReceiptState,
    BrokerTransition,
    DispatchPermit,
    IdempotentCreateReplayPermit,
    PrimaryBrokerLedger,
    ProviderWorkerLeaseCoordinator,
    WorkerDispatchRefused,
    WorkerLease,
    WorkerLeaseBusy,
    WorkerLeaseStale,
    WorkerLeaseStatus,
    WorkerLeaseUnavailable,
    WorkerReplayRefused,
    authorization_from_mapping,
    provider_idempotency_token,
)

FIXTURE = Path(__file__).parent / "fixtures/provider_broker_protocol_vectors.json"
NOW = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)
INTENT = BrokerDispatchIntent(
    "1" * 64,
    provider_idempotency_token("1" * 64, "2" * 64, "3" * 64),
    "2" * 64,
    "3" * 64,
    "2026-07-17T00:00:00Z",
)


def _ready(tmp_path: Path, clock: list[datetime] | None = None, *, timeout: float = 0.1):
    current = clock or [NOW]
    ledger = PrimaryBrokerLedger(tmp_path / "broker.sqlite", clock=lambda: current[0])
    ledger.ensure_schema()
    authorization = authorization_from_mapping(
        json.loads(FIXTURE.read_text(encoding="utf-8"))["authorization"]
    )
    operation = ledger.authorize(authorization)
    coordinator = ProviderWorkerLeaseCoordinator(
        ledger,
        tmp_path / "worker.sqlite",
        clock=lambda: current[0],
        lease_ttl_seconds=10,
        lock_timeout_seconds=timeout,
    )
    coordinator.ensure_schema()
    return coordinator, ledger, operation, current


def _hold_process(
    root: str, ready: multiprocessing.Queue[bool], release: multiprocessing.Queue[bool]
) -> None:
    coordinator, _, _, _ = _ready(Path(root), timeout=2.0)
    with coordinator.session("tenant-1", "op-key-1", "process-a"):
        ready.put(True)
        release.get(timeout=5)


def _crash_process(root: str, ready: multiprocessing.Queue[bool]) -> None:
    coordinator, _, _, _ = _ready(Path(root), timeout=2.0)
    coordinator.session("tenant-1", "op-key-1", "crashed")
    ready.put(True)
    time.sleep(0.1)
    os._exit(23)


def test_exact_idempotent_create_replay_is_recovery_only_fenced_and_single_use(
    tmp_path: Path,
) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "first") as first:
        dispatch = first.prepare_dispatch(INTENT)
        assert isinstance(dispatch, DispatchPermit)
        first.assert_permit_active(dispatch)

    with coordinator.session("tenant-1", "op-key-1", "recovery") as recovery:
        permit = recovery.prepare_idempotent_create_replay(INTENT)
        assert isinstance(permit, IdempotentCreateReplayPermit)
        with pytest.raises(WorkerReplayRefused, match="already issued"):
            recovery.prepare_idempotent_create_replay(INTENT)
        assert recovery.assert_replay_permit_active(permit).dispatch_intent == INTENT
        with pytest.raises(WorkerReplayRefused, match="already issued"):
            recovery.prepare_idempotent_create_replay(INTENT)

    with coordinator.session("tenant-1", "op-key-1", "successor") as successor:
        later = successor.prepare_idempotent_create_replay(INTENT)
        assert later.fence > permit.fence
        assert later.dispatch_intent == permit.dispatch_intent


def test_replay_refuses_substitution_expiry_and_first_send_state(tmp_path: Path) -> None:
    coordinator, _, _, clock = _ready(tmp_path)
    expiring = replace(INTENT, replay_expires_at="2026-07-16T18:30:05Z")
    changed = replace(
        expiring,
        qualification_digest="4" * 64,
        provider_idempotency_token=provider_idempotency_token(
            expiring.request_envelope_digest, expiring.adapter_contract_digest, "4" * 64
        ),
    )
    with coordinator.session("tenant-1", "op-key-1", "first") as first:
        with pytest.raises(WorkerReplayRefused, match="recovery-only"):
            first.prepare_idempotent_create_replay(expiring)
        first.prepare_dispatch(expiring)
    with coordinator.session("tenant-1", "op-key-1", "recovery") as recovery:
        with pytest.raises(WorkerReplayRefused, match="differs"):
            recovery.prepare_idempotent_create_replay(changed)
        clock[0] += timedelta(seconds=5)
        with pytest.raises(WorkerReplayRefused, match="expired"):
            recovery.prepare_idempotent_create_replay(expiring)


def test_first_dispatch_refuses_unbounded_replay_window(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    unbounded = replace(INTENT, replay_expires_at="2026-07-18T18:30:01Z")
    with (
        coordinator.session("tenant-1", "op-key-1", "first") as first,
        pytest.raises(WorkerDispatchRefused, match="live and bounded"),
    ):
        first.prepare_dispatch(unbounded)


def test_session_holds_flock_across_prepare_until_exit(tmp_path: Path) -> None:
    coordinator, ledger, operation, _ = _ready(tmp_path)
    session = coordinator.session("tenant-1", "op-key-1", "worker-a")
    with session:
        assert session.status is WorkerLeaseStatus.AUTHORIZED
        with pytest.raises(WorkerLeaseBusy):
            coordinator.session("tenant-1", "op-key-1", "worker-b")
        permit = session.prepare_dispatch(INTENT)
        assert isinstance(permit, DispatchPermit)
        assert permit.operation_id == operation.operation_id
        assert permit.authorization_digest == operation.authorization_digest
        assert permit.route_digest == operation.route_digest
        assert permit.marked_version == 1
        assert permit.process_id == os.getpid()
        assert session.assert_permit_active(permit).send_marker
        with pytest.raises(WorkerLeaseStale, match="already consumed"):
            session.assert_permit_active(permit)
        assert session.status is WorkerLeaseStatus.RECOVERY_ONLY
        with pytest.raises(WorkerDispatchRefused, match="already exists"):
            session.prepare_dispatch(INTENT)
    assert ledger.lookup("tenant-1", "op-key-1").operation.send_marker
    with pytest.raises(WorkerLeaseStale, match="exited"):
        session.refresh()


def test_attempt_and_command_are_deterministic_across_holders_fences_and_time(
    tmp_path: Path,
) -> None:
    coordinator, _, _, clock = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker-a") as first:
        attempt = first.lease.attempt_id
    clock[0] += timedelta(seconds=3)
    with coordinator.session("tenant-1", "op-key-1", "worker-b") as second:
        assert second.lease.fence == 2
        assert second.lease.attempt_id == attempt
        permit = second.prepare_dispatch(INTENT)
    assert permit.command_id == coordinator._command_id(second.lease.operation_id)  # noqa: SLF001


def test_cancellation_before_marker_is_durable_and_successor_can_dispatch(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with pytest.raises(KeyboardInterrupt), coordinator.session("tenant-1", "op-key-1", "worker-a"):
        raise KeyboardInterrupt
    with sqlite3.connect(tmp_path / "worker.sqlite") as db:
        assert (
            db.execute(
                "SELECT event_type FROM worker_lease_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()[0]
            == "cancelled"
        )
    with coordinator.session("tenant-1", "op-key-1", "worker-b") as successor:
        assert successor.lease.fence == 2
        successor.prepare_dispatch(INTENT)


def test_crash_after_primary_marker_reconstructs_recovery_but_never_permit(tmp_path: Path) -> None:
    coordinator, ledger, _, _ = _ready(tmp_path)
    coordinator._after_primary_dispatch = lambda: (_ for _ in ()).throw(
        WorkerLeaseUnavailable("crash boundary")
    )  # noqa: SLF001
    with (
        pytest.raises(WorkerLeaseUnavailable),
        coordinator.session("tenant-1", "op-key-1", "worker-a") as session,
    ):
        session.prepare_dispatch(INTENT)
    marked = ledger.lookup("tenant-1", "op-key-1").operation
    assert marked is not None and marked.send_marker
    coordinator._after_primary_dispatch = lambda: None  # noqa: SLF001
    with coordinator.session("tenant-1", "op-key-1", "worker-b") as recovery:
        assert recovery.status is WorkerLeaseStatus.RECOVERY_ONLY
        assert recovery.refresh() == marked
        with pytest.raises(WorkerDispatchRefused):
            recovery.prepare_dispatch(INTENT)


def test_terminal_primary_state_classifies_terminal(tmp_path: Path) -> None:
    coordinator, ledger, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker-a") as session:
        session.prepare_dispatch(INTENT)
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "terminal-command",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=1,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    with coordinator.session("tenant-1", "op-key-1", "worker-b") as terminal:
        assert terminal.status is WorkerLeaseStatus.TERMINAL
        assert terminal.refresh().state is BrokerReceiptState.CHARGED
        with pytest.raises(WorkerDispatchRefused):
            terminal.prepare_dispatch(INTENT)
    assert coordinator.verify_integrity() == 1
    with coordinator.session("tenant-1", "op-key-1", "worker-c") as terminal_again:
        assert terminal_again.status is WorkerLeaseStatus.TERMINAL


def test_expiry_does_not_bypass_live_flock_and_expired_owner_cannot_prepare(tmp_path: Path) -> None:
    coordinator, _, _, clock = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker-a") as session:
        clock[0] += timedelta(seconds=11)
        with pytest.raises(WorkerLeaseBusy):
            coordinator.session("tenant-1", "op-key-1", "worker-b")
        with pytest.raises(WorkerLeaseStale, match="dispatch window"):
            session.prepare_dispatch(INTENT)


def test_clock_rollback_before_acquisition_never_commits_marker(tmp_path: Path) -> None:
    coordinator, ledger, _, clock = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker") as session:
        try:
            clock[0] -= timedelta(seconds=1)
            with pytest.raises(WorkerLeaseStale, match="dispatch window"):
                session.prepare_dispatch(INTENT)
        finally:
            clock[0] = NOW
    operation = ledger.lookup("tenant-1", "op-key-1").operation
    assert operation is not None and operation.send_marker is False


def test_clock_rollback_during_cleanup_rolls_back_without_chain_corruption(tmp_path: Path) -> None:
    coordinator, _, _, clock = _ready(tmp_path)
    session = coordinator.session("tenant-1", "op-key-1", "worker")
    session.__enter__()
    clock[0] -= timedelta(seconds=1)
    with pytest.raises(WorkerLeaseUnavailable, match="time moved backward"):
        session.__exit__(None, None, None)
    clock[0] = NOW
    assert coordinator.verify_integrity() == 1
    with coordinator.session("tenant-1", "op-key-1", "successor") as successor:
        assert successor.lease.fence == 2


def test_expired_authorization_never_receives_dispatch_permit(tmp_path: Path) -> None:
    _, ledger, _, clock = _ready(tmp_path)
    coordinator = ProviderWorkerLeaseCoordinator(
        ledger,
        tmp_path / "worker.sqlite",
        clock=lambda: clock[0],
        lease_ttl_seconds=30_000,
        lock_timeout_seconds=0.1,
    )
    with coordinator.session("tenant-1", "op-key-1", "worker-a") as session:
        clock[0] = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)
        with pytest.raises(WorkerDispatchRefused, match="authorization"):
            session.prepare_dispatch(INTENT)
    operation = ledger.lookup("tenant-1", "op-key-1").operation
    assert operation is not None and operation.send_marker is False


def test_permit_cannot_be_consumed_after_authorization_expiry(tmp_path: Path) -> None:
    _, ledger, _, clock = _ready(tmp_path)
    coordinator = ProviderWorkerLeaseCoordinator(
        ledger,
        tmp_path / "worker.sqlite",
        clock=lambda: clock[0],
        lease_ttl_seconds=30_000,
        lock_timeout_seconds=0.1,
    )
    with coordinator.session("tenant-1", "op-key-1", "worker") as session:
        permit = session.prepare_dispatch(INTENT)
        clock[0] = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)
        with pytest.raises(WorkerLeaseStale, match="authorization"):
            session.assert_permit_active(permit)


def test_thread_contender_cannot_enter_live_session(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "winner"):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(coordinator.session, "tenant-1", "op-key-1", f"loser-{index}")
                for index in range(4)
            ]
        assert all(isinstance(future.exception(), WorkerLeaseBusy) for future in futures)


def test_wrong_thread_entry_does_not_poison_owner_session(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    session = coordinator.session("tenant-1", "op-key-1", "owner")
    with ThreadPoolExecutor(max_workers=1) as pool:
        failure = pool.submit(session.__enter__).exception()
    assert isinstance(failure, WorkerLeaseStale)
    with session:
        assert session.status is WorkerLeaseStatus.AUTHORIZED


def test_wrong_thread_exit_cannot_revoke_owner_session(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "owner") as session:
        with ThreadPoolExecutor(max_workers=1) as pool:
            failure = pool.submit(session.__exit__, None, None, None).exception()
        assert isinstance(failure, WorkerLeaseStale)
        with pytest.raises(WorkerLeaseBusy):
            coordinator.session("tenant-1", "op-key-1", "contender")
        assert session.refresh().send_marker is False


def test_distinct_sidecars_share_primary_operation_flock(tmp_path: Path) -> None:
    first, ledger, _, clock = _ready(tmp_path)
    second = ProviderWorkerLeaseCoordinator(
        ledger,
        tmp_path / "another-worker.sqlite",
        clock=lambda: clock[0],
        lease_ttl_seconds=10,
        lock_timeout_seconds=0.1,
    )
    second.ensure_schema()
    with first.session("tenant-1", "op-key-1", "worker-a"), pytest.raises(WorkerLeaseBusy):
        second.session("tenant-1", "op-key-1", "worker-b")


def test_operation_lock_rejects_symlink_substitution(tmp_path: Path) -> None:
    coordinator, _, operation, _ = _ready(tmp_path)
    digest = hashlib.sha256(operation.operation_id.encode("ascii")).hexdigest()
    lock_path = coordinator._lock_dir / f"{digest}.lock"  # noqa: SLF001
    lock_path.symlink_to(tmp_path / "attacker-controlled")
    with pytest.raises(WorkerLeaseUnavailable, match="lock is unavailable"):
        coordinator.session("tenant-1", "op-key-1", "worker")


def test_preexisting_primary_marker_never_returns_permit(tmp_path: Path) -> None:
    coordinator, ledger, operation, _ = _ready(tmp_path)
    attempt_id = coordinator._attempt_id(operation.operation_id)  # noqa: SLF001
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            coordinator._command_id(operation.operation_id),  # noqa: SLF001
            0,
            BrokerReceiptState.DISPATCH_POSSIBLE,
            attempt_id=attempt_id,
            dispatch_intent=INTENT,
        ),
    )
    with coordinator.session("tenant-1", "op-key-1", "worker") as recovery:
        assert recovery.status is WorkerLeaseStatus.RECOVERY_ONLY
        with pytest.raises(WorkerDispatchRefused):
            recovery.prepare_dispatch(INTENT)


def test_session_requires_context_and_abandonment_releases_flock(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    abandoned = coordinator.session("tenant-1", "op-key-1", "worker-a")
    with pytest.raises(WorkerLeaseStale, match="not entered"):
        abandoned.prepare_dispatch(INTENT)
    del abandoned
    gc.collect()
    with coordinator.session("tenant-1", "op-key-1", "worker-b") as successor:
        assert successor.lease.fence == 2


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork semantics")
def test_forked_child_cannot_use_inherited_session(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "parent") as session:
        permit = session.prepare_dispatch(INTENT)
        child = os.fork()
        if child == 0:
            try:
                session.__exit__(None, None, None)
            except WorkerLeaseStale:
                os._exit(0)
            os._exit(1)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert session.assert_permit_active(permit).send_marker


def test_cleanup_failure_does_not_mask_body_failure(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    session = coordinator.session("tenant-1", "op-key-1", "worker")
    coordinator._close_session = lambda *_args, **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]  # noqa: SLF001
        WorkerLeaseUnavailable("cleanup failed")
    )
    with pytest.raises(RuntimeError, match="body failed") as raised, session:
        raise RuntimeError("body failed")
    assert any("cleanup also failed" in note for note in raised.value.__notes__)


def test_process_flock_and_crash_release(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    release = context.Queue()
    process = context.Process(target=_hold_process, args=(str(tmp_path), ready, release))
    process.start()
    assert ready.get(timeout=5)
    coordinator, _, _, _ = _ready(tmp_path)
    with pytest.raises(WorkerLeaseBusy):
        coordinator.session("tenant-1", "op-key-1", "parent")
    release.put(True)
    process.join(timeout=5)
    assert process.exitcode == 0
    with coordinator.session("tenant-1", "op-key-1", "parent") as successor:
        assert successor.lease.fence == 2


def test_abrupt_process_crash_releases_flock_and_fence_advances(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    process = context.Process(target=_crash_process, args=(str(tmp_path), ready))
    process.start()
    assert ready.get(timeout=5)
    process.join(timeout=5)
    assert process.exitcode == 23
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "successor") as successor:
        assert successor.lease.fence == 2


@pytest.mark.parametrize("corruption", ["trigger", "table", "event", "row"])
def test_schema_trigger_and_event_corruption_fail_closed(tmp_path: Path, corruption: str) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker"):
        pass
    with sqlite3.connect(tmp_path / "worker.sqlite") as db:
        if corruption == "trigger":
            db.execute("DROP TRIGGER worker_events_no_delete")
        elif corruption == "table":
            db.execute("ALTER TABLE worker_leases ADD COLUMN poison TEXT")
        else:
            if corruption == "event":
                db.execute("DROP TRIGGER worker_events_no_update")
                db.execute(
                    "UPDATE worker_lease_events SET event_hash=? WHERE sequence=1", ("0" * 64,)
                )
                db.execute(
                    "CREATE TRIGGER worker_events_no_update BEFORE UPDATE ON worker_lease_events BEGIN SELECT RAISE(ABORT, 'worker lease events are append-only'); END"
                )
            else:
                db.execute("UPDATE worker_leases SET holder_id='substituted'")
    with pytest.raises(WorkerLeaseUnavailable):
        coordinator.verify_integrity()


def test_corrupt_prior_row_is_not_overwritten_by_takeover(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker"):
        pass
    with sqlite3.connect(tmp_path / "worker.sqlite") as db:
        db.execute("UPDATE worker_leases SET holder_id='substituted'")
    with pytest.raises(WorkerLeaseUnavailable, match="event authority"):
        coordinator.session("tenant-1", "op-key-1", "successor")


def test_hash_valid_same_fence_resurrection_fails_integrity(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker"):
        pass
    with coordinator._transaction() as db:  # noqa: SLF001
        row = db.execute("SELECT * FROM worker_leases").fetchone()
        lease = WorkerLease(
            row["operation_id"],
            row["tenant_id"],
            row["idempotency_key"],
            row["holder_id"],
            row["fence"],
            row["attempt_id"],
            row["acquired_at"],
            row["expires_at"],
        )
        db.execute(
            "UPDATE worker_leases SET status='active' WHERE operation_id=?", (row["operation_id"],)
        )
        coordinator._append_event(  # noqa: SLF001
            db,
            lease,
            "acquired",
            row["expires_at"],
        )
    with pytest.raises(WorkerLeaseUnavailable, match="progression"):
        coordinator.verify_integrity()


def test_orphan_event_chain_fails_integrity(tmp_path: Path) -> None:
    coordinator, _, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker"):
        pass
    with sqlite3.connect(tmp_path / "worker.sqlite") as db:
        db.execute("DROP TRIGGER worker_leases_no_delete")
        db.execute("DELETE FROM worker_leases")
        db.execute(
            "CREATE TRIGGER worker_leases_no_delete BEFORE DELETE ON worker_leases "
            "BEGIN SELECT RAISE(ABORT, 'worker lease history is durable'); END"
        )
    with pytest.raises(WorkerLeaseUnavailable, match="no current row"):
        coordinator.verify_integrity()


def test_hash_valid_terminal_regression_fails_integrity(tmp_path: Path) -> None:
    coordinator, ledger, _, _ = _ready(tmp_path)
    with coordinator.session("tenant-1", "op-key-1", "worker") as session:
        session.prepare_dispatch(INTENT)
    ledger.transition(
        "tenant-1",
        "op-key-1",
        BrokerTransition(
            "terminal-command",
            1,
            BrokerReceiptState.CHARGED,
            charge_cents=1,
            evidence_digest="b" * 64,
            output_digest="c" * 64,
        ),
    )
    with coordinator.session("tenant-1", "op-key-1", "terminal"):
        pass
    with coordinator._transaction() as db:  # noqa: SLF001
        row = db.execute("SELECT * FROM worker_leases").fetchone()
        lease = WorkerLease(
            row["operation_id"],
            row["tenant_id"],
            row["idempotency_key"],
            "forged-recovery",
            row["fence"] + 1,
            row["attempt_id"],
            row["expires_at"],
            row["expires_at"],
        )
        db.execute("DROP TRIGGER worker_recovery_irreversible")
        db.execute(
            "UPDATE worker_leases SET holder_id=?,fence=?,acquired_at=?,expires_at=?,status=?",
            (lease.holder_id, lease.fence, lease.acquired_at, lease.expires_at, "recovery_only"),
        )
        coordinator._append_event(db, lease, "recovered", lease.acquired_at)  # noqa: SLF001
        db.execute(
            "CREATE TRIGGER worker_recovery_irreversible BEFORE UPDATE OF status ON worker_leases "
            "WHEN (OLD.status = 'recovery_only' AND NEW.status NOT IN ('recovery_only','terminal')) "
            "OR (OLD.status = 'terminal' AND NEW.status != 'terminal') "
            "BEGIN SELECT RAISE(ABORT, 'worker recovery status is irreversible'); END"
        )
    with pytest.raises(WorkerLeaseUnavailable, match="terminal history"):
        coordinator.verify_integrity()


def test_sidecar_is_separate_and_api_has_no_transport(tmp_path: Path) -> None:
    coordinator, ledger, _, _ = _ready(tmp_path)
    assert coordinator._path != ledger._path  # noqa: SLF001
    forbidden = {"send", "retry", "transport", "request", "dispatch"}
    assert forbidden.isdisjoint(name for name in dir(coordinator) if not name.startswith("_"))
