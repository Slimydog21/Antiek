from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import UnknownCallOutcome
from substrate.midnight_oil.contracts import (
    ResearchAcceptancePolicy,
    research_acceptance_policy_authority_fields,
)
from substrate.midnight_oil.job_store import (
    CompareAndSetResult,
    InvalidStoredJob,
    OperationState,
)
from substrate.midnight_oil.operation_queue import (
    DurableOperationQueue,
    provider_idempotency_key,
)
from substrate.midnight_oil.worker import (
    FakeClock,
    LeaseValidationError,
    WorkerStepResult,
    lease_authorized_operation,
    run_leased_worker_iteration,
)
from tests.test_midnight_oil_consent_routes import _client, _create

HEADER = "X-Midnight-Oil-Spend-Consent"


def _authorized(tmp_path: Path):  # type: ignore[no-untyped-def]
    client, deps = _client(tmp_path)
    queue = DurableOperationQueue(tmp_path / "operations.sqlite3")
    wired = replace(deps, operation_queue=queue)
    client.app.state.midnight_oil_dependencies = wired
    _create(client)
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert issued.status_code == 200
    return client, wired, queue, issued.json()["token"]


def _run(client, token: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned"},
    )


def _leased_authorized(tmp_path: Path):  # type: ignore[no-untyped-def]
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    return deps, queue, operation_id, lease


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


def test_claim_before_cas_failure_recovers_same_operation(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    original = deps.owner_jobs.compare_and_set

    def crash(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("claim-to-cas crash")

    deps.owner_jobs.compare_and_set = crash  # type: ignore[method-assign]
    failed = _run(client, token)
    assert failed.status_code == 503
    assert failed.headers["cache-control"] == "no-store"
    assert "claim-to-cas" not in failed.text
    deps.owner_jobs.compare_and_set = original  # type: ignore[method-assign]
    recovered = _run(client, token)
    assert recovered.status_code == 200
    assert recovered.json()["state"] == "queued"
    assert queue.get(recovered.json()["operation_id"]) is not None


def test_cas_before_insert_failure_repairs_queue(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    original = queue.enqueue_once

    def crash(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("cas-to-insert crash")

    queue.enqueue_once = crash  # type: ignore[method-assign]
    failed = _run(client, token)
    assert failed.status_code == 503
    assert "cas-to-insert" not in failed.text
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.operation_state.value == "queued"
    queue.enqueue_once = original  # type: ignore[method-assign]
    assert _run(client, token).status_code == 200
    assert queue.get(authority.operation_id or "missing") is not None


def test_exact_replay_rejects_changed_durable_execution_options(tmp_path: Path) -> None:
    client, _, queue, token = _authorized(tmp_path)
    first = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", "max_steps": 1, "auto_deposit": False},
    )
    assert first.status_code == 200
    changed = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", "max_steps": 99, "auto_deposit": True},
    )
    assert changed.status_code == 409
    assert "options conflict" in changed.text
    queued = queue.get(first.json()["operation_id"])
    assert queued is not None
    assert queued.options["max_steps"] == 1
    assert queued.options["auto_deposit"] is False


def test_terminal_replay_rejects_changed_archived_options(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    first = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", "max_steps": 1},
    )
    operation_id = first.json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-terminal",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert deps.owner_jobs.compare_and_set(
        owner_user_id="alice",
        job_id="job-owned",
        expected_version=authority.state_version,
        expected_state=OperationState.RUNNING,
        operation_id=operation_id,
        next_state=OperationState.COMPLETE,
        completed_at_ms=1_000_002,
    ).applied
    assert queue.acknowledge_terminal(
        operation_id=operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        terminal_state="complete",
        completed_at_ms=1_000_003,
    )

    replay = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", "max_steps": 99},
    )
    assert replay.status_code == 409
    assert "terminal queue" in replay.text


def test_terminal_replay_rejects_changed_archived_identity(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-terminal-identity",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert deps.owner_jobs.compare_and_set(
        owner_user_id="alice",
        job_id="job-owned",
        expected_version=authority.state_version,
        expected_state=OperationState.RUNNING,
        operation_id=operation_id,
        next_state=OperationState.COMPLETE,
        completed_at_ms=1_000_002,
    ).applied
    assert queue.acknowledge_terminal(
        operation_id=operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        terminal_state="complete",
        completed_at_ms=1_000_003,
    )
    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            "UPDATE midnight_oil_operation_terminal SET owner_user_id = ? "
            "WHERE operation_id = ?",
            ("mallory", operation_id),
        )

    replay = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned", "max_steps": 1},
    )
    assert replay.status_code == 409
    assert "terminal queue" in replay.text


def test_enqueue_binds_exact_policy_receipt_and_config_across_restart(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    queued = DurableOperationQueue(queue.path).get(operation_id)

    assert authority is not None
    assert queued is not None
    assert queued.options["consent_receipt_id"] == authority.consent_receipt_id
    assert queued.options["consent_config_hash"] == authority.consent_config_hash
    expected_policy = research_acceptance_policy_authority_fields(
        ResearchAcceptancePolicy()
    )
    assert {key: queued.options[key] for key in expected_policy} == expected_policy
    assert {key: authority.payload[key] for key in expected_policy} == expected_policy


def test_owner_policy_drift_refuses_before_running_or_queue_lease(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    payload = dict(authority.payload)
    payload["acceptance_policy_unsupported_output"] = "discard"
    deps.owner_jobs._jobs[("alice", "job-owned")] = replace(  # type: ignore[attr-defined]
        authority, payload=payload
    )
    budget_path = Path(deps.jobs.budget_db_path())
    existed_before = budget_path.exists()

    with pytest.raises(LeaseValidationError, match="reconciliation"):
        lease_authorized_operation(
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-drift",
            now_ms=1_000_001,
            lease_expires_at_ms=1_060_001,
        )

    after = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    queued = queue.get(operation_id)
    assert after is not None and after.operation_state is OperationState.QUEUED
    assert after.dispatch_started_at_ms is None
    assert queued is not None and queued.state == "queued" and queued.leased_at_ms is None
    assert budget_path.exists() is existed_before


def test_queue_config_drift_refuses_before_running_or_queue_lease(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    queued = queue.get(operation_id)
    assert queued is not None
    options = dict(queued.options)
    options["consent_config_hash"] = "0" * 64
    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            "UPDATE midnight_oil_operation_queue SET options_json = ? WHERE operation_id = ?",
            (json.dumps(options, sort_keys=True, separators=(",", ":")), operation_id),
        )

    with pytest.raises(LeaseValidationError, match="reconciliation"):
        lease_authorized_operation(
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-drift",
            now_ms=1_000_001,
            lease_expires_at_ms=1_060_001,
        )

    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    after = queue.get(operation_id)
    assert authority is not None and authority.operation_state is OperationState.QUEUED
    assert authority.dispatch_started_at_ms is None
    assert after is not None and after.state == "queued" and after.leased_at_ms is None


def test_queue_authority_race_refuses_before_owner_running(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]

    class DriftOnLease:
        def get(self, requested: str):  # type: ignore[no-untyped-def]
            return queue.get(requested)

        def lease(self, **kwargs):  # type: ignore[no-untyped-def]
            current = queue.get(operation_id)
            assert current is not None
            options = dict(current.options)
            options["consent_config_hash"] = "0" * 64
            with sqlite3.connect(queue.path) as connection:
                connection.execute(
                    "UPDATE midnight_oil_operation_queue SET options_json = ? "
                    "WHERE operation_id = ?",
                    (
                        json.dumps(options, sort_keys=True, separators=(",", ":")),
                        operation_id,
                    ),
                )
            return queue.lease(**kwargs)

    with pytest.raises(LeaseValidationError, match="lease did not persist"):
        lease_authorized_operation(
            operation_queue=DriftOnLease(),  # type: ignore[arg-type]
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-race",
            now_ms=1_000_001,
            lease_expires_at_ms=1_060_001,
        )

    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.operation_state is OperationState.QUEUED
    assert authority.dispatch_started_at_ms is None


def test_queue_identity_race_refuses_before_owner_running(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]

    class DriftIdentityOnLease:
        def get(self, requested: str):  # type: ignore[no-untyped-def]
            return queue.get(requested)

        def lease(self, **kwargs):  # type: ignore[no-untyped-def]
            with sqlite3.connect(queue.path) as connection:
                connection.execute(
                    "UPDATE midnight_oil_operation_queue SET owner_user_id = ? "
                    "WHERE operation_id = ?",
                    ("mallory", operation_id),
                )
            return queue.lease(**kwargs)

    with pytest.raises(LeaseValidationError, match="lease did not persist"):
        lease_authorized_operation(
            operation_queue=DriftIdentityOnLease(),  # type: ignore[arg-type]
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-identity-race",
            now_ms=1_000_001,
            lease_expires_at_ms=1_060_001,
        )

    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.operation_state is OperationState.QUEUED
    assert authority.dispatch_started_at_ms is None


def test_token_is_header_only_and_duplicate_rejected(tmp_path: Path) -> None:
    client, _, _, token = _authorized(tmp_path)
    assert client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "alice"},
        json={"job_id": "job-owned", "token": token},
    ).status_code == 422
    assert client.post(
        f"/midnight-oil/run?consent={token}",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned"},
    ).status_code == 400
    leaked = client.post(
        f"/midnight-oil/run?x={token}",
        headers={"x-test-user": "alice", HEADER: token},
        json={"job_id": "job-owned"},
    )
    assert leaked.status_code == 400
    duplicate = client.post(
        "/midnight-oil/run",
        headers=[("x-test-user", "alice"), (HEADER, token), (HEADER, token)],
        json={"job_id": "job-owned"},
    )
    assert duplicate.status_code == 400


def test_wrong_owner_and_config_drift_fail_without_enqueue(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    wrong = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "mallory", HEADER: token},
        json={"job_id": "job-owned"},
    )
    assert wrong.status_code == 404
    raw = deps.jobs.get_job("job-owned")
    assert raw is not None
    raw["duration_minutes"] = 31
    deps.jobs.put_job(raw)
    assert _run(client, token).status_code == 409
    with sqlite3.connect(queue.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM midnight_oil_operation_queue"
        ).fetchone() == (0,)


def test_worker_has_one_lease_and_stable_step_idempotency(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    response = _run(client, token)
    operation_id = response.json()["operation_id"]
    first = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    with pytest.raises(ValueError, match="already leased"):
        lease_authorized_operation(
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-b",
            now_ms=1_000_002,
            lease_expires_at_ms=1_060_002,
        )
    assert first.operation_id == operation_id
    assert provider_idempotency_key(operation_id, 0) == provider_idempotency_key(operation_id, 0)
    assert provider_idempotency_key(operation_id, 0) != provider_idempotency_key(operation_id, 1)


def test_lease_recheck_normalizes_malformed_authority_for_quarantine(
    tmp_path: Path,
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    deps.owner_jobs.get_job = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        InvalidStoredJob("corrupt authority canary")
    )
    with pytest.raises(ValueError, match="durable operation is malformed") as caught:
        lease_authorized_operation(
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="worker-a",
            now_ms=1_000_001,
            lease_expires_at_ms=1_060_001,
        )
    assert "corrupt authority canary" not in str(caught.value)


def test_worker_propagates_key_and_same_worker_resumes_before_dispatch(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    resumed = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_002,
        lease_expires_at_ms=1_060_002,
    )
    assert resumed.step_index == lease.step_index == 0
    captured: list[str] = []

    def paid_step(job, idempotency_key):  # type: ignore[no-untyped-def]
        del job
        captured.append(idempotency_key)
        return WorkerStepResult(spent_usd=0.01, spawn_id="spawn-1", done=True)

    result = run_leased_worker_iteration(
        resumed,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        step_fn=paid_step,
        project_fn=lambda job: 0.01,
        clock=FakeClock(1_000_002),
    )
    assert result.status == "complete"
    assert captured == [provider_idempotency_key(operation_id, 0)]
    assert queue.get(operation_id).next_step_index == 1  # type: ignore[union-attr]


def test_expired_exact_replay_repairs_claim_to_cas(tmp_path: Path) -> None:
    client, deps, _, token = _authorized(tmp_path)
    original = deps.owner_jobs.compare_and_set

    def crash(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("after claim")

    deps.owner_jobs.compare_and_set = crash  # type: ignore[method-assign]
    assert _run(client, token).status_code == 503
    deps.owner_jobs.compare_and_set = original  # type: ignore[method-assign]
    object.__setattr__(deps, "clock_ms", lambda: 1_900_001)
    repaired = _run(client, token)
    assert repaired.status_code == 200, repaired.text
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.consent_claimed_at_ms == 1_000_000


def test_checkpoint_before_step_advance_retries_without_provider_redispatch(
    tmp_path: Path,
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    calls: list[str] = []

    def paid_step(job, key):  # type: ignore[no-untyped-def]
        del job
        calls.append(key)
        return WorkerStepResult(spent_usd=0.01, spawn_id="spawn-1", done=True)

    original_hook = queue._after_fenced_action

    def crash_after_action() -> None:
        raise RuntimeError("checkpoint crash")

    queue._after_fenced_action = crash_after_action  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="checkpoint"):
        run_leased_worker_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=paid_step,
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_000_002),
        )
    queue._after_fenced_action = original_hook  # type: ignore[method-assign]
    resumed = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_003,
        lease_expires_at_ms=1_060_003,
    )
    result = run_leased_worker_iteration(
        resumed,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        step_fn=paid_step,
        project_fn=lambda job: 0.01,
        clock=FakeClock(1_000_003),
    )
    assert result.status == "complete"
    assert len(calls) == 1
    assert queue.get(operation_id).next_step_index == 1  # type: ignore[union-attr]


def test_stale_lease_generation_cannot_enter_paid_boundary(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    stale = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_010_001,
    )
    current = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-b",
        now_ms=1_010_001,
        lease_expires_at_ms=1_020_001,
    )
    assert current.lease_generation > stale.lease_generation
    assert not queue.validate_lease(
        operation_id=operation_id,
        worker_id=stale.worker_id,
        lease_generation=stale.lease_generation,
        now_ms=1_010_002,
    )
    before = deps.jobs.get_job("job-owned")
    provider_calls: list[str] = []
    with pytest.raises(RuntimeError, match="stale"):
        run_leased_worker_iteration(
            stale,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=lambda job, key: (
                provider_calls.append(key)
                or WorkerStepResult(spent_usd=0.01, done=True)
            ),
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_010_002),
        )
    assert provider_calls == []
    assert deps.jobs.get_job("job-owned") == before


def test_provider_returned_but_unsettled_step_requires_reconciliation(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    key = lease.idempotency_key(0)
    raw = deps.jobs.get_job("job-owned")
    assert raw is not None
    raw["status"] = "failed"
    raw["returned_step_keys"] = [key]
    raw["completed_step_keys"] = []
    deps.jobs.put_job(raw)
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="settlement reconciliation"):
        run_leased_worker_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=lambda job, provider_key: (
                calls.append(provider_key)
                or WorkerStepResult(spent_usd=0.01, done=True)
            ),
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_000_002),
        )
    assert calls == []
    assert queue.get(operation_id).next_step_index == 0  # type: ignore[union-attr]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE


def test_provider_exception_and_lost_authority_cas_require_reconciliation(
    tmp_path: Path,
) -> None:
    deps, queue, _, lease = _leased_authorized(tmp_path)
    current = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert current is not None and current.operation_state is OperationState.RUNNING
    original = deps.owner_jobs.compare_and_set
    deps.owner_jobs.compare_and_set = lambda **kwargs: CompareAndSetResult(  # type: ignore[method-assign]
        applied=False, job=current
    )
    try:
        with pytest.raises(
            RuntimeError, match="exception-path authority requires reconciliation"
        ) as caught:
            run_leased_worker_iteration(
                lease,
                operation_queue=queue,
                owner_jobs=deps.owner_jobs,
                store=deps.jobs,
                step_fn=lambda job, key: (_ for _ in ()).throw(
                    TimeoutError("provider-internal-canary")
                ),
                project_fn=lambda job: 0.01,
                clock=FakeClock(1_000_002),
            )
    finally:
        deps.owner_jobs.compare_and_set = original  # type: ignore[method-assign]
    assert isinstance(caught.value.__cause__, UnknownCallOutcome)
    assert "provider-internal-canary" not in str(caught.value)


def test_provider_exception_does_not_overwrite_concurrently_terminal_authority(
    tmp_path: Path,
) -> None:
    deps, queue, operation_id, lease = _leased_authorized(tmp_path)

    def finish_then_fail(job, key):  # type: ignore[no-untyped-def]
        del job, key
        current = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
        assert current is not None
        changed = deps.owner_jobs.compare_and_set(
            owner_user_id="alice",
            job_id="job-owned",
            expected_version=current.state_version,
            expected_state=OperationState.RUNNING,
            operation_id=operation_id,
            next_state=OperationState.COMPLETE,
            completed_at_ms=1_000_002,
        )
        assert changed.applied
        raise TimeoutError("late provider observer")

    with pytest.raises(UnknownCallOutcome):
        run_leased_worker_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=finish_then_fail,
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_000_002),
        )
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.operation_state is OperationState.COMPLETE


def test_pre_dispatch_validation_failure_does_not_invent_unknown_spend(
    tmp_path: Path,
) -> None:
    deps, queue, _, lease = _leased_authorized(tmp_path)
    provider_calls: list[str] = []
    with pytest.raises(ValueError, match="project_fn result must be positive"):
        run_leased_worker_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=lambda job, key: (
                provider_calls.append(key) or WorkerStepResult(spent_usd=0.01, done=True)
            ),
            project_fn=lambda job: 0.0,
            clock=FakeClock(1_000_002),
        )
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None and authority.operation_state is OperationState.FAILED
    assert provider_calls == []


def test_durable_coordinator_serializes_expired_takeover_after_paid_writes(
    tmp_path: Path,
) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    old = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="old-worker",
        now_ms=1_000_001,
        lease_expires_at_ms=1_010_001,
    )
    entered = threading.Event()
    release = threading.Event()
    takeover_done = threading.Event()
    order: list[str] = []

    def old_paid_boundary() -> None:
        def action() -> tuple[None, bool]:
            entered.set()
            assert release.wait(timeout=5)
            order.append("old-write")
            return None, False

        queue.run_fenced(
            operation_id=operation_id,
            worker_id=old.worker_id,
            lease_generation=old.lease_generation,
            now_ms=1_000_002,
            expected_step_index=0,
            action=action,
        )

    def takeover() -> None:
        queue.lease(
            operation_id=operation_id,
            worker_id="new-worker",
            leased_at_ms=1_010_001,
            lease_expires_at_ms=1_020_001,
        )
        order.append("takeover")
        takeover_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        old_future = pool.submit(old_paid_boundary)
        assert entered.wait(timeout=5)
        new_future = pool.submit(takeover)
        assert not takeover_done.wait(timeout=0.1)
        release.set()
        old_future.result(timeout=5)
        new_future.result(timeout=5)
    assert order == ["old-write", "takeover"]


def test_different_operations_execute_fenced_actions_concurrently(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "concurrent-operations.sqlite3")
    options = {
        "max_steps": None,
        "auto_deposit": False,
        "draft_combined": True,
        "force_offline": False,
    }
    for index in (1, 2):
        queue.enqueue_once(
            operation_id=f"operation-{index}",
            owner_user_id=f"owner-{index}",
            job_id=f"job-{index}",
            enqueued_at_ms=1,
            options=options,
        )
        queue.lease(
            operation_id=f"operation-{index}",
            worker_id=f"worker-{index}",
            leased_at_ms=2,
            lease_expires_at_ms=10_000,
        )
    barrier = threading.Barrier(2)

    def execute(index: int) -> int:
        return queue.run_fenced(
            operation_id=f"operation-{index}",
            worker_id=f"worker-{index}",
            lease_generation=1,
            now_ms=3,
            expected_step_index=0,
            action=lambda: (barrier.wait(timeout=5), False),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, (1, 2)))
    assert sorted(results) == [0, 1]


def test_provider_crossing_lease_expiry_advances_inside_operation_fence(tmp_path: Path) -> None:
    client, deps, queue, token = _authorized(tmp_path)
    operation_id = _run(client, token).json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        jobs=deps.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="worker-a",
        now_ms=1_000_001,
        lease_expires_at_ms=1_000_010,
    )
    clock = FakeClock(1_000_002)

    def slow_paid_step(job, key):  # type: ignore[no-untyped-def]
        del job, key
        clock.advance(100)
        return WorkerStepResult(spent_usd=0.01, done=True)

    result = run_leased_worker_iteration(
        lease,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        step_fn=slow_paid_step,
        project_fn=lambda job: 0.01,
        clock=clock,
    )
    assert result.status == "complete"
    assert queue.get(operation_id).next_step_index == 1  # type: ignore[union-attr]


def test_queue_discovers_claimable_and_archives_terminal_once(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "worker-queue.sqlite3")
    queued, inserted = queue.enqueue_once(
        operation_id="operation-runtime",
        owner_user_id="owner-runtime",
        job_id="job-runtime",
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    assert inserted
    assert queue.next_claimable(now_ms=10) == queued
    leased, won = queue.lease(
        operation_id=queued.operation_id,
        worker_id="worker-runtime",
        leased_at_ms=11,
        lease_expires_at_ms=20,
    )
    assert won
    assert queue.next_claimable(now_ms=19) is None
    assert queue.next_claimable(now_ms=20) == leased
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="worker-runtime",
        lease_generation=leased.lease_generation,
        terminal_state="complete",
        completed_at_ms=21,
    )
    assert queue.get(leased.operation_id) is None
    assert queue.next_claimable(now_ms=22) is None
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="worker-runtime",
        lease_generation=leased.lease_generation,
        terminal_state="complete",
        completed_at_ms=22,
    )
    with pytest.raises(ValueError, match="already terminal"):
        queue.enqueue_once(
            operation_id="operation-runtime",
            owner_user_id="owner-runtime",
            job_id="job-runtime",
            enqueued_at_ms=23,
            options={
                "max_steps": None,
                "auto_deposit": True,
                "draft_combined": True,
                "force_offline": False,
            },
        )


def test_terminal_acknowledgement_is_generation_fenced(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "worker-queue.sqlite3")
    queue.enqueue_once(
        operation_id="operation-runtime",
        owner_user_id="owner-runtime",
        job_id="job-runtime",
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    leased, _ = queue.lease(
        operation_id="operation-runtime",
        worker_id="worker-runtime",
        leased_at_ms=11,
        lease_expires_at_ms=20,
    )
    assert not queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="worker-runtime",
        lease_generation=leased.lease_generation + 1,
        terminal_state="complete",
        completed_at_ms=12,
    )
    assert queue.get(leased.operation_id) is not None


def test_paid_fence_renews_same_generation_before_releasing_lock(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "worker-queue.sqlite3")
    queue.enqueue_once(
        operation_id="operation-renew",
        owner_user_id="owner-renew",
        job_id="job-renew",
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    leased, _ = queue.lease(
        operation_id="operation-renew",
        worker_id="worker-renew",
        leased_at_ms=11,
        lease_expires_at_ms=20,
    )
    result = queue.run_fenced(
        operation_id=leased.operation_id,
        worker_id="worker-renew",
        lease_generation=leased.lease_generation,
        now_ms=12,
        expected_step_index=0,
        action=lambda: ("paid-return", True),
        renew_expires_at_ms=lambda: 200,
    )
    assert result == "paid-return"
    renewed = queue.get(leased.operation_id)
    assert renewed is not None
    assert renewed.lease_generation == leased.lease_generation
    assert renewed.lease_expires_at_ms == 200
    assert renewed.next_step_index == 1


def test_exceptional_paid_fence_renews_before_exposing_takeover(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "worker-queue.sqlite3")
    queue.enqueue_once(
        operation_id="operation-error-renew",
        owner_user_id="owner-renew",
        job_id="job-renew",
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    leased, _ = queue.lease(
        operation_id="operation-error-renew",
        worker_id="worker-renew",
        leased_at_ms=11,
        lease_expires_at_ms=20,
    )

    def timeout_after_provider() -> tuple[str, bool]:
        raise RuntimeError("ambiguous provider timeout")

    with pytest.raises(RuntimeError, match="ambiguous provider timeout"):
        queue.run_fenced(
            operation_id=leased.operation_id,
            worker_id="worker-renew",
            lease_generation=leased.lease_generation,
            now_ms=12,
            expected_step_index=0,
            action=timeout_after_provider,
            renew_expires_at_ms=lambda: 200,
        )
    renewed = queue.get(leased.operation_id)
    assert renewed is not None
    assert renewed.lease_generation == leased.lease_generation
    assert renewed.lease_expires_at_ms == 200
    assert queue.next_claimable(now_ms=199) is None
