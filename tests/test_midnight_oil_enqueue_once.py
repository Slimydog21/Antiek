from __future__ import annotations

import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.midnight_oil.job_store import OwnerBoundDurableJobStore, SqliteDurableJobStore
from substrate.midnight_oil.operation_queue import (
    DurableOperationQueue,
    provider_idempotency_key,
)
from substrate.midnight_oil.product_path import run_authorized_job
from substrate.midnight_oil.worker import (
    FakeClock,
    WorkerStepResult,
    lease_authorized_operation,
    run_leased_worker_iteration,
)
from tests.test_midnight_oil_consent_routes import dependencies, make_client

HEADER = "X-Midnight-Oil-Spend-Consent"


def _authorized(tmp_path: Path):  # type: ignore[no-untyped-def]
    queue = DurableOperationQueue(tmp_path / "operations.sqlite3")
    deps = dependencies(tmp_path, operation_queue=queue)
    client = make_client(deps)
    created = client.post(
        "/midnight-oil/create",
        headers={"x-authenticated-test-user": "alice"},
        json={
            "job_id": "job-owned",
            "goals": ["Investigate durable consent"],
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 200, created.text
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-authenticated-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert issued.status_code == 200, issued.text
    return client, deps, queue, issued.json()["token"]


def _run(client, token: str, **body: object):  # type: ignore[no-untyped-def]
    return client.post(
        "/midnight-oil/run",
        headers={"x-authenticated-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", **body},
    )


def test_fifty_concurrent_requests_create_one_durable_queue_row(tmp_path: Path) -> None:
    client, _, queue, token = _authorized(tmp_path)
    barrier = threading.Barrier(50)

    def submit(_: int) -> int:
        barrier.wait()
        return _run(client, token).status_code

    with ThreadPoolExecutor(max_workers=50) as pool:
        statuses = list(pool.map(submit, range(50)))
    assert statuses == [200] * 50
    with sqlite3.connect(queue.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT operation_id) "
            "FROM midnight_oil_operation_queue"
        ).fetchone() == (1, 1)


def test_claim_before_cas_failure_recovers_exact_operation(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    original = deps.jobs.compare_and_set_authority

    def crash(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("claim-to-cas secret marker")

    deps.jobs.compare_and_set_authority = crash  # type: ignore[method-assign]
    failed = _run(client, token)
    assert failed.status_code == 503
    assert token not in failed.text and "secret marker" not in failed.text
    deps.jobs.compare_and_set_authority = original  # type: ignore[method-assign]
    recovered = _run(client, token)
    assert recovered.status_code == 200
    assert recovered.json()["state"] == "dispatch_claimed"
    assert queue.get(recovered.json()["operation_id"]) is not None


def test_cas_before_enqueue_failure_repairs_after_restart(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    original = queue.enqueue_once

    def crash(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("cas-to-enqueue secret marker")

    queue.enqueue_once = crash  # type: ignore[method-assign]
    failed = _run(client, token)
    assert failed.status_code == 503
    durable = deps.jobs.get_job_for_owner("job-owned", "alice")
    assert durable is not None and durable.authority is not None
    assert durable.authority.operation_state == "dispatch_claimed"
    queue.enqueue_once = original  # type: ignore[method-assign]
    restarted = DurableOperationQueue(queue.path)
    object.__setattr__(deps, "operation_queue", restarted)
    recovered = _run(client, token)
    assert recovered.status_code == 200
    assert restarted.get(recovered.json()["operation_id"]) is not None


def test_token_is_header_only_redacted_and_never_persisted(
    tmp_path: Path, caplog
) -> None:  # type: ignore[no-untyped-def]
    client, _, queue, token = _authorized(tmp_path)
    caplog.set_level(logging.DEBUG)
    body = client.post(
        "/midnight-oil/run",
        headers={"x-authenticated-test-user": "alice"},
        json={"job_id": "job-owned", "token": token},
    )
    assert body.status_code == 422 and token not in body.text
    query = client.post(
        f"/midnight-oil/run?consent={token}",
        headers={"x-authenticated-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned"},
    )
    assert query.status_code == 400 and token not in query.text
    server_logs = "\n".join(
        record.getMessage() for record in caplog.records if not record.name.startswith("httpx")
    )
    assert token not in server_logs
    with sqlite3.connect(queue.path) as connection:
        rows = connection.execute("SELECT * FROM midnight_oil_operation_queue").fetchall()
    assert token not in repr(rows)


def test_exact_replay_converges_without_replacing_durable_options(tmp_path: Path) -> None:
    client, _, queue, token = _authorized(tmp_path)
    first = _run(client, token, max_steps=1, auto_deposit=True)
    replay = _run(client, token, max_steps=99, draft_combined=False)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    row = queue.get(first.json()["operation_id"])
    assert row is not None
    assert row.options == {
        "max_steps": None,
        "auto_deposit": False,
        "draft_combined": True,
        "force_offline": True,
    }


def test_queued_running_and_terminal_replays_do_not_enqueue_again(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    queued = _run(client, token)
    operation_id = queued.json()["operation_id"]
    durable = deps.jobs.get_job_for_owner("job-owned", "alice")
    assert durable is not None and durable.authority is not None
    started = deps.jobs.compare_and_set_authority(
        "job-owned",
        "alice",
        expected_version=durable.authority.state_version,
        expected_state="dispatch_claimed",
        expected_operation_id=operation_id,
        operation_id=operation_id,
        next_state="dispatch_started",
        dispatch_started_at_ms=1_001,
    )
    assert started is not None and _run(client, token).json()["state"] == "dispatch_started"
    assert started.authority is not None
    terminal = deps.jobs.compare_and_set_authority(
        "job-owned",
        "alice",
        expected_version=started.authority.state_version,
        expected_state="dispatch_started",
        expected_operation_id=operation_id,
        operation_id=operation_id,
        next_state="dispatch_finished",
        dispatch_completed_at_ms=1_002,
    )
    assert terminal is not None and _run(client, token).json()["state"] == "dispatch_finished"
    with sqlite3.connect(queue.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM midnight_oil_operation_queue"
        ).fetchone() == (1,)


def test_queue_lease_is_atomic_and_provider_key_is_stable(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "queue.sqlite3")
    operation_id = "operation-1"
    queue.enqueue_once(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": False,
            "draft_combined": True,
            "force_offline": True,
        },
    )
    first, won = queue.lease(
        operation_id=operation_id,
        worker_id="worker-a",
        leased_at_ms=2,
        lease_expires_at_ms=100,
    )
    second, lost = queue.lease(
        operation_id=operation_id,
        worker_id="worker-b",
        leased_at_ms=3,
        lease_expires_at_ms=101,
    )
    assert won and not lost and second.lease_owner == first.lease_owner == "worker-a"
    assert provider_idempotency_key(operation_id, 0) == provider_idempotency_key(operation_id, 0)
    assert provider_idempotency_key(operation_id, 0) != provider_idempotency_key(operation_id, 1)


def test_restart_after_paid_checkpoint_does_not_redispatch(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    durable = deps.jobs.get_job_for_owner("job-owned", "alice")
    assert durable is not None
    execution = OwnerBoundDurableJobStore(deps.jobs, "alice")
    lease = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        owner_jobs=deps.jobs,
        operation_queue=queue,
        jobs=execution,
        worker_id="worker-a",
        now_ms=1_001,
        lease_expires_at_ms=2_000,
    )
    calls: list[str] = []

    def paid_step(job, key: str) -> WorkerStepResult:  # type: ignore[no-untyped-def]
        calls.append(key)
        return WorkerStepResult(spent_usd=0.01, done=True)

    original_hook = queue._after_fenced_action
    queue._after_fenced_action = lambda: (_ for _ in ()).throw(RuntimeError("crash"))
    with pytest.raises(RuntimeError, match="crash"):
        run_leased_worker_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.jobs,
            store=execution,
            step_fn=paid_step,
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_002),
        )
    queue._after_fenced_action = original_hook
    restarted = DurableOperationQueue(queue.path)
    reopened_authority = SqliteDurableJobStore(deps.jobs.db_path)
    reopened_execution = OwnerBoundDurableJobStore(reopened_authority, "alice")
    resumed = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        owner_jobs=reopened_authority,
        operation_queue=restarted,
        jobs=reopened_execution,
        worker_id="worker-a",
        now_ms=1_003,
        lease_expires_at_ms=2_001,
    )
    result = run_leased_worker_iteration(
        resumed,
        operation_queue=restarted,
        owner_jobs=reopened_authority,
        store=reopened_execution,
        step_fn=paid_step,
        project_fn=lambda job: 0.01,
        clock=FakeClock(1_003),
    )
    assert result.status == "complete"
    assert calls == [provider_idempotency_key(operation_id, 0)]
    assert restarted.get(operation_id).next_step_index == 1  # type: ignore[union-attr]


def test_expired_exact_replay_repairs_claim_to_cas(tmp_path: Path) -> None:
    client, deps, _, token = _authorized(tmp_path)
    original = deps.jobs.compare_and_set_authority
    deps.jobs.compare_and_set_authority = (  # type: ignore[method-assign]
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("after claim"))
    )
    assert _run(client, token).status_code == 503
    deps.jobs.compare_and_set_authority = original  # type: ignore[method-assign]
    object.__setattr__(deps, "clock_ms", lambda: 2_000_000)
    repaired = _run(client, token)
    assert repaired.status_code == 200
    durable = SqliteDurableJobStore(deps.jobs.db_path).get_job_for_owner("job-owned", "alice")
    assert durable is not None and durable.authority is not None
    assert durable.authority.dispatch_claimed_at_ms == 1_000


def test_stale_lease_generation_cannot_enter_paid_boundary(tmp_path: Path) -> None:
    client, _, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    stale, won = queue.lease(
        operation_id=operation_id,
        worker_id="worker-a",
        leased_at_ms=1_001,
        lease_expires_at_ms=1_010,
    )
    assert won
    current, taken = queue.lease(
        operation_id=operation_id,
        worker_id="worker-b",
        leased_at_ms=1_010,
        lease_expires_at_ms=2_000,
    )
    assert taken and current.lease_generation > stale.lease_generation
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="stale"):
        queue.run_fenced(
            operation_id=operation_id,
            worker_id="worker-a",
            lease_generation=stale.lease_generation,
            now_ms=1_011,
            expected_step_index=0,
            action=lambda: (calls.append("paid"), True),
        )
    assert calls == []


def test_provider_returned_unsettled_checkpoint_survives_sqlite_restart(
    tmp_path: Path,
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    execution = OwnerBoundDurableJobStore(deps.jobs, "alice")
    lease = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        owner_jobs=deps.jobs,
        operation_queue=queue,
        jobs=execution,
        worker_id="worker-a",
        now_ms=1_001,
        lease_expires_at_ms=2_000,
    )
    row = execution.get_job("job-owned")
    assert row is not None
    row["status"] = "failed"
    row["returned_step_keys"] = [lease.idempotency_key(0)]
    execution.put_job(row)
    reopened = SqliteDurableJobStore(deps.jobs.db_path)
    reopened_execution = OwnerBoundDurableJobStore(reopened, "alice")
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="settlement reconciliation"):
        run_leased_worker_iteration(
            lease,
            operation_queue=DurableOperationQueue(queue.path),
            owner_jobs=reopened,
            store=reopened_execution,
            step_fn=lambda job, key: (
                calls.append(key) or WorkerStepResult(spent_usd=0.01, done=True)
            ),
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_002),
        )
    assert calls == []
    stored = reopened.get_job_for_owner("job-owned", "alice")
    assert stored is not None and stored.returned_step_keys == (lease.idempotency_key(0),)
    assert stored.authority is not None and stored.authority.operation_state == "failed_closed"


def test_expired_takeover_waits_for_inflight_operation_fence(tmp_path: Path) -> None:
    client, _, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    old, _ = queue.lease(
        operation_id=operation_id,
        worker_id="old",
        leased_at_ms=1_001,
        lease_expires_at_ms=1_010,
    )
    entered = threading.Event()
    release = threading.Event()
    takeover_done = threading.Event()
    order: list[str] = []

    def paid_boundary() -> None:
        def action():  # type: ignore[no-untyped-def]
            entered.set()
            assert release.wait(timeout=5)
            order.append("old-write")
            return None, False

        queue.run_fenced(
            operation_id=operation_id,
            worker_id="old",
            lease_generation=old.lease_generation,
            now_ms=1_002,
            expected_step_index=0,
            action=action,
        )

    def takeover() -> None:
        queue.lease(
            operation_id=operation_id,
            worker_id="new",
            leased_at_ms=1_010,
            lease_expires_at_ms=2_000,
        )
        order.append("takeover")
        takeover_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        old_future = pool.submit(paid_boundary)
        assert entered.wait(timeout=5)
        new_future = pool.submit(takeover)
        assert not takeover_done.wait(timeout=0.1)
        release.set()
        old_future.result(timeout=5)
        new_future.result(timeout=5)
    assert order == ["old-write", "takeover"]


def test_provider_crossing_lease_expiry_completes_under_existing_fence(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    execution = OwnerBoundDurableJobStore(deps.jobs, "alice")
    lease = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        owner_jobs=deps.jobs,
        operation_queue=queue,
        jobs=execution,
        worker_id="worker-a",
        now_ms=1_001,
        lease_expires_at_ms=1_010,
    )
    clock = FakeClock(1_002)

    def slow_step(job, key):  # type: ignore[no-untyped-def]
        clock.advance(100)
        return WorkerStepResult(spent_usd=0.01, done=True)

    result = run_leased_worker_iteration(
        lease,
        operation_queue=queue,
        owner_jobs=deps.jobs,
        store=execution,
        step_fn=slow_step,
        project_fn=lambda job: 0.01,
        clock=clock,
    )
    assert result.status == "complete"
    assert queue.get(operation_id).next_step_index == 1  # type: ignore[union-attr]


def test_production_execution_entry_propagates_durable_provider_key(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    calls: list[str] = []
    final = run_authorized_job(
        operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        authority_store=deps.jobs,
        operation_queue=queue,
        worker_id="production-worker",
        now_ms=1_001,
        lease_duration_ms=999,
        step_fn=lambda job, key: (
            calls.append(key) or WorkerStepResult(spent_usd=0.01, done=True)
        ),
        project_fn=lambda job: 0.01,
    )
    assert final.status == "complete"
    assert calls == [provider_idempotency_key(operation_id, 0)]
    reopened = SqliteDurableJobStore(deps.jobs.db_path).get_job_for_owner(
        "job-owned", "alice"
    )
    assert reopened is not None
    assert reopened.completed_step_keys == (provider_idempotency_key(operation_id, 0),)


def test_checkpoint_columns_reject_non_string_arrays_after_restart(tmp_path: Path) -> None:
    _, deps, _, _ = _authorized(tmp_path)
    with sqlite3.connect(deps.jobs.db_path) as connection:
        connection.execute(
            "UPDATE midnight_oil_jobs SET completed_step_keys_json = ? "
            "WHERE owner_user_id = ? AND job_id = ?",
            ('["valid", 7]', "alice", "job-owned"),
        )
    reopened = SqliteDurableJobStore(deps.jobs.db_path)
    with pytest.raises(ValueError, match="array of strings"):
        reopened.get_job_for_owner("job-owned", "alice")


def test_slow_nonterminal_step_reacquires_from_current_clock_without_redispatch(
    tmp_path: Path,
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    clock = FakeClock(1_001)
    calls: list[str] = []

    def slow_two_step(job, key):  # type: ignore[no-untyped-def]
        calls.append(key)
        if len(calls) == 1:
            clock.advance(25)  # crosses the initial 1_011 lease boundary
            return WorkerStepResult(spent_usd=0.01, spawn_id="first", done=False)
        return WorkerStepResult(spent_usd=0.01, spawn_id="second", done=True)

    final = run_authorized_job(
        operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        authority_store=deps.jobs,
        operation_queue=queue,
        worker_id="slow-worker",
        now_ms=1_001,
        lease_duration_ms=10,
        max_steps=2,
        advance_ms_per_step=0,
        step_fn=slow_two_step,
        project_fn=lambda job: 0.01,
        clock=clock,
    )
    expected = [
        provider_idempotency_key(operation_id, 0),
        provider_idempotency_key(operation_id, 1),
    ]
    assert calls == expected
    assert final.status == "complete"
    reopened_store = SqliteDurableJobStore(deps.jobs.db_path)
    reopened = reopened_store.get_job_for_owner("job-owned", "alice")
    assert reopened is not None
    assert reopened.completed_step_keys == tuple(expected)
    assert reopened.spawn_ids == ("first", "second")
    assert reopened.authority is not None
    assert reopened.authority.operation_state == "dispatch_finished"
    reopened_queue = DurableOperationQueue(queue.path).get(operation_id)
    assert reopened_queue is not None
    assert reopened_queue.next_step_index == 2
    assert reopened_queue.lease_generation == 2


@pytest.mark.parametrize("lease_duration_ms", [True, 0, -1])
def test_authorized_runner_rejects_nonpositive_lease_durations(
    tmp_path: Path, lease_duration_ms: object
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    with pytest.raises(ValueError, match="positive integer"):
        run_authorized_job(
            operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            authority_store=deps.jobs,
            operation_queue=queue,
            worker_id="worker",
            now_ms=1_001,
            lease_duration_ms=lease_duration_ms,  # type: ignore[arg-type]
            step_fn=lambda job, key: WorkerStepResult(spent_usd=0.01, done=True),
            project_fn=lambda job: 0.01,
        )


def test_authorized_runner_rejects_lease_deadline_overflow(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    with pytest.raises(ValueError, match="durable integer range"):
        run_authorized_job(
            operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            authority_store=deps.jobs,
            operation_queue=queue,
            worker_id="worker",
            now_ms=2**63 - 1,
            lease_duration_ms=1,
            step_fn=lambda job, key: WorkerStepResult(spent_usd=0.01, done=True),
            project_fn=lambda job: 0.01,
        )
