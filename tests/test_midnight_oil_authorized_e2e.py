from __future__ import annotations

import logging
import secrets
import traceback
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.engagement_routes import (
    register_engagement_routes,
    reset_engagement_stores,
)
from interfaces.research.api.midnight_oil_routes import (
    MidnightOilDependencies,
    register_midnight_oil_routes,
)
from substrate.midnight_oil.budget_ledger import (
    BudgetLedger,
    UnknownCallOutcome,
    UnknownOutcomePersistenceError,
)
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.job import InMemoryJobStore
from substrate.midnight_oil.job_store import (
    DurableOwnerJobStore,
    OperationState,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryOwnerStore,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.spend_consent import SpendConsentStore
from substrate.midnight_oil.worker import (
    FakeClock,
    WorkerStepResult,
    lease_authorized_operation,
    run_leased_worker_iteration,
)


def _dependencies(root: Path, *, production: bool = False) -> MidnightOilDependencies:
    key = b"integration-signing-key-material!!"
    common = dict(
        owner_jobs=DurableOwnerJobStore(root / "owner.duckdb"),
        jobs=DurableJobStore(root / "details.sqlite3"),
        consents=SpendConsentStore(root / "consents.sqlite3"),
        active_key_id="integration-key",
        signing_key=key,
        verification_keys={"integration-key": key},
        operation_queue=DurableOperationQueue(root / "queue.sqlite3"),
    )
    if production:
        return MidnightOilDependencies(**common)  # type: ignore[arg-type]
    return MidnightOilDependencies(
        **common,  # type: ignore[arg-type]
        clock_ms=lambda: 1_000_000,
        random_token=secrets.token_urlsafe,
        test_mode=True,
    )


def _client(deps: MidnightOilDependencies) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        user = request.headers.get("x-test-user")
        if user:
            request.state.user_id = user
        return await call_next(request)

    register_midnight_oil_routes(app, dependencies=deps)
    register_engagement_routes(app)
    return TestClient(app)


def test_restart_safe_authorized_path_produces_html_twins_without_token_retention(
    tmp_path: Path,
) -> None:
    engagement_root = tmp_path / "engagement-state"
    reset_engagement_stores(root=engagement_root)
    headers = {"x-test-user": "alice"}
    deps = _dependencies(tmp_path)
    client = _client(deps)
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["Establish the strongest evidence."], "duration_minutes": 10},
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]

    # Restart after create: every authority is reconstructed from disk.
    deps = _dependencies(tmp_path)
    client = _client(deps)
    issued = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True},
    )
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]

    # Restart after consent, then enqueue the exact signed operation.
    deps = _dependencies(tmp_path)
    client = _client(deps)
    queued = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": token},
        json={"job_id": job_id},
    )
    assert queued.status_code == 200, queued.text
    operation_id = queued.json()["operation_id"]

    # Restart after enqueue and lease one fake paid provider step.
    deps = _dependencies(tmp_path)
    lease = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id=job_id,
        owner_jobs=deps.owner_jobs,
        operation_queue=deps.operation_queue,  # type: ignore[arg-type]
        jobs=deps.jobs,
        worker_id="integration-worker",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    provider_keys: list[str] = []

    def fake_provider(job, key):  # type: ignore[no-untyped-def]
        del job
        provider_keys.append(key)
        return WorkerStepResult(
            spent_usd=0.01,
            spawn_id="integration-spawn",
            output_text="Evidence-backed result.",
            insights=("One durable insight",),
            questions=("What remains uncertain?",),
            done=True,
        )

    result = run_leased_worker_iteration(
        lease,
        operation_queue=deps.operation_queue,  # type: ignore[arg-type]
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        step_fn=fake_provider,
        project_fn=lambda job: 0.01,
        clock=FakeClock(1_000_002),
    )
    assert result.status == "complete"
    assert len(provider_keys) == 1
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id=job_id)
    assert authority is not None and authority.operation_state is OperationState.COMPLETE

    # Restart after worker completion and deposit the exact authorized snapshot.
    deps = _dependencies(tmp_path)
    client = _client(deps)
    deposited = client.post(
        "/midnight-oil/deposit", headers=headers, json={"job_id": job_id}
    )
    assert deposited.status_code == 200, deposited.text
    body = deposited.json()
    assert body["view_format"] == "html"
    assert "<" in body["html"] and "pdf" not in body["html"].lower()
    assert body["twin_count"] >= 2
    reset_engagement_stores(root=engagement_root)
    restarted_client = _client(_dependencies(tmp_path))
    twins = restarted_client.get(
        f"/engagement/twins/{body['asset_id']}", headers=headers
    )
    assert twins.status_code == 200
    assert len(twins.json()["notes"]) >= 2

    canaries = (token.encode(), b"integration-signing-key-material!!")
    persisted = b"".join(
        path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    )
    assert all(canary not in persisted for canary in canaries)


def test_live_startup_dependency_matrix_fails_before_serving(tmp_path: Path) -> None:
    from interfaces.research.api.app import create_app

    valid = _dependencies(tmp_path, production=True)
    app = create_app(enable_midnight_oil=True, midnight_oil_dependencies=valid)
    paths = {getattr(route, "path", None) for route in app.routes}
    for included in app.routes:
        router = getattr(included, "original_router", None)
        if router is not None:
            paths.update(getattr(route, "path", None) for route in router.routes)
    assert "/midnight-oil/run" in paths

    class OwnerSubclass(DurableOwnerJobStore):
        pass

    class JobSubclass(DurableJobStore):
        pass

    class QueueSubclass(DurableOperationQueue):
        pass

    invalid_overrides: tuple[dict[str, object], ...] = (
        {"owner_jobs": MemoryOwnerStore()},
        {"owner_jobs": OwnerSubclass(tmp_path / "owner-subclass.duckdb")},
        {"jobs": InMemoryJobStore()},
        {"jobs": JobSubclass(tmp_path / "job-subclass.sqlite3")},
        {"consents": object()},
        {"operation_queue": None},
        {"operation_queue": object()},
        {"operation_queue": QueueSubclass(tmp_path / "queue-subclass.sqlite3")},
        {"verification_keys": {}},
        {"signing_key": b"short"},
        {"active_key_id": " invalid "},
        {"clock_ms": None},
        {"clock_ms": lambda: 1},
        {"random_token": None},
        {"random_token": lambda size: "repeated-token-value"},
        {"random_token": lambda size: f"predictable-{size}"},
    )
    for override in invalid_overrides:
        with pytest.raises(ValueError):
            MidnightOilDependencies(**{**valid.__dict__, **override})

    with pytest.raises(RuntimeError, match="validated durable dependencies"):
        create_app(enable_midnight_oil=True)


def test_hostile_controls_fail_independently_and_unknown_spend_reconciles(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    headers = {"x-test-user": "alice"}
    deps = _dependencies(tmp_path)
    client = _client(deps)
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["hostile matrix"], "duration_minutes": 10},
    ).json()
    job_id = created["job_id"]
    issued = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True},
    ).json()
    token = issued["token"]

    assert client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "mallory", "X-Midnight-Oil-Spend-Consent": token},
        json={"job_id": job_id},
    ).status_code == 404
    assert deps.operation_queue.get(issued["operation_id"]) is None  # type: ignore[union-attr]

    raw = deps.jobs.get_job(job_id)
    assert raw is not None
    raw["duration_minutes"] = 11
    deps.jobs.put_job(raw)
    drift = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": token},
        json={"job_id": job_id},
    )
    assert drift.status_code == 409
    raw["duration_minutes"] = 10
    deps.jobs.put_job(raw)

    queued = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": token},
        json={"job_id": job_id},
    )
    assert queued.status_code == 200
    operation_id = queued.json()["operation_id"]
    with pytest.raises(ValueError, match="conflicts"):
        deps.operation_queue.enqueue_once(  # type: ignore[union-attr]
            operation_id=operation_id,
            owner_user_id="alice",
            job_id=job_id,
            enqueued_at_ms=1_000_000,
            options={
                "max_steps": 2,
                "auto_deposit": False,
                "draft_combined": True,
                "force_offline": False,
            },
        )

    lease = lease_authorized_operation(
        operation_id=operation_id,
        owner_user_id="alice",
        job_id=job_id,
        owner_jobs=deps.owner_jobs,
        operation_queue=deps.operation_queue,  # type: ignore[arg-type]
        jobs=deps.jobs,
        worker_id="crashing-worker",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )

    provider_canary = "CANARY-PROVIDER-FAILURE-SECRET"
    provider_calls = 0

    def unknown_provider(job, key):  # type: ignore[no-untyped-def]
        nonlocal provider_calls
        del job, key
        provider_calls += 1
        raise TimeoutError(provider_canary)

    try:
        run_leased_worker_iteration(
            lease,
            operation_queue=deps.operation_queue,  # type: ignore[arg-type]
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            step_fn=unknown_provider,
            project_fn=lambda job: 0.01,
            clock=FakeClock(1_000_002),
        )
    except UnknownCallOutcome as caught:
        caught_text = str(caught)
        formatted_trace = "".join(traceback.format_exception(caught))
        logging.getLogger("midnight-oil-test").exception("provider outcome quarantined")
    else:
        raise AssertionError("provider timeout must remain unknown")
    assert provider_canary not in caught_text
    assert provider_canary not in formatted_trace
    assert deps.operation_queue.get(operation_id).next_step_index == 0  # type: ignore[union-attr]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id=job_id)
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE
    assert BudgetLedger(deps.jobs.budget_db_path()).balance(job_id).held_cents == 1

    # Reopen every durable boundary before recovery. Owner authority, rather
    # than the execution snapshot or an unexpired in-process lease, must make a
    # second provider dispatch ineligible.
    deps = _dependencies(tmp_path)
    with pytest.raises(ValueError, match="not dispatchable"):
        lease_authorized_operation(
            operation_id=operation_id,
            owner_user_id="alice",
            job_id=job_id,
            owner_jobs=deps.owner_jobs,
            operation_queue=deps.operation_queue,  # type: ignore[arg-type]
            jobs=deps.jobs,
            worker_id="restart-worker",
            now_ms=1_060_002,
            lease_expires_at_ms=1_120_002,
        )
    recovered = run_leased_worker_iteration(
        lease,
        operation_queue=deps.operation_queue,  # type: ignore[arg-type]
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        step_fn=unknown_provider,
        project_fn=lambda job: 0.01,
        clock=FakeClock(1_000_003),
    )
    assert recovered.status == "failed"
    assert provider_calls == 1
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id=job_id)
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE
    assert BudgetLedger(deps.jobs.budget_db_path()).balance(job_id).held_cents == 1
    deposited = client.post(
        "/midnight-oil/deposit", headers=headers, json={"job_id": job_id}
    )
    assert deposited.status_code == 200
    persisted = b"".join(
        path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    )
    failure_surfaces = "\n".join(
        (caplog.text, deposited.text, repr(deps.owner_jobs), repr(deps.operation_queue))
    )
    assert provider_canary not in failure_surfaces
    assert provider_canary.encode() not in persisted


def test_unknown_persistence_failure_trace_redacts_both_internal_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = BudgetLedger(str(tmp_path / "failure-ledger.duckdb"))
    ledger.ensure_schema()
    ledger.reserve("run", 10, {"research": 10})
    provider_canary = "CANARY-PROVIDER-INTERNAL"
    bookkeeping_canary = "CANARY-BOOKKEEPING-INTERNAL"

    def fail_unknown(hold):  # type: ignore[no-untyped-def]
        del hold
        raise RuntimeError(bookkeeping_canary)

    ledger._mark_hold_unknown = fail_unknown  # type: ignore[method-assign]

    def provider_failure() -> tuple[str, int]:
        raise TimeoutError(provider_canary)

    try:
        ledger.guarded_call("run", "research", 1, provider_failure)
    except UnknownOutcomePersistenceError as caught:
        caught_text = str(caught)
        formatted = "".join(traceback.format_exception(caught))
        logging.getLogger("midnight-oil-test").exception(
            "unknown persistence quarantined"
        )
    else:
        raise AssertionError("bookkeeping failure must surface a typed quarantine")
    public_surfaces = "\n".join((caught_text, formatted, caplog.text))
    assert provider_canary not in public_surfaces
    assert bookkeeping_canary not in public_surfaces


def test_failure_canary_absent_from_logs_errors_schema_html_and_storage(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deps = _dependencies(tmp_path)
    client = _client(deps)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["leak scan"], "duration_minutes": 5},
    )
    job_id = created.json()["job_id"]
    issued = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True},
    )
    assert issued.status_code == 200
    canary = "CANARY-RAW-SPEND-TOKEN-DO-NOT-RETAIN.abcdef"
    rejected = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": canary},
        json={"job_id": job_id},
    )
    assert rejected.status_code == 403
    surfaces = "\n".join(
        (
            rejected.text,
            caplog.text,
            created.text,
            client.get("/openapi.json").text,
        )
    )
    persisted = b"".join(
        path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    )
    assert canary not in surfaces
    assert canary.encode() not in persisted


def test_altered_operation_and_ceiling_cannot_cross_signed_authority(tmp_path: Path) -> None:
    deps = _dependencies(tmp_path)
    client = _client(deps)
    headers = {"x-test-user": "alice"}

    def create_and_issue(goal: str) -> tuple[str, str]:
        created = client.post(
            "/midnight-oil/create",
            headers=headers,
            json={"goals": [goal], "duration_minutes": 5},
        ).json()
        issued = client.post(
            f"/midnight-oil/jobs/{created['job_id']}/spend-consent",
            headers=headers,
            json={"use_recommended": True},
        ).json()
        return created["job_id"], issued["token"]

    first_job, first_token = create_and_issue("first")
    _, second_token = create_and_issue("second")
    wrong_operation = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": second_token},
        json={"job_id": first_job},
    )
    assert wrong_operation.status_code == 403

    original_get = deps.owner_jobs.get_job

    def altered_ceiling(*, owner_user_id: str, job_id: str):  # type: ignore[no-untyped-def]
        row = original_get(owner_user_id=owner_user_id, job_id=job_id)
        if row is None or job_id != first_job:
            return row
        assert row.approved_ceiling_cents is not None
        return replace(row, approved_ceiling_cents=row.approved_ceiling_cents + 1)

    deps.owner_jobs.get_job = altered_ceiling  # type: ignore[method-assign]
    wrong_ceiling = client.post(
        "/midnight-oil/run",
        headers={**headers, "X-Midnight-Oil-Spend-Consent": first_token},
        json={"job_id": first_job},
    )
    assert wrong_ceiling.status_code == 403
