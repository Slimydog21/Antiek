"""Hermetic proof of the durable Midnight Oil authorized product path.

This suite deliberately reconstructs every dependency at each boundary.  A
passing request therefore cannot rely on process-local authority or queue
state.  The provider is a deterministic fake; live provider billing is not
proved here and remains operator-gated.
"""

from __future__ import annotations

import base64
import json
import logging
import sqlite3
from dataclasses import fields
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_routes import (
    MidnightOilDependencies,
    production_dependencies_from_env,
    register_midnight_oil_routes,
)
from substrate.engagement_spine.store import FileEngagementStore
from substrate.midnight_oil.budget_ledger import UnknownCallOutcome
from substrate.midnight_oil.deposit import deposit_job_results
from substrate.midnight_oil.job_store import OwnerBoundDurableJobStore, SqliteDurableJobStore
from substrate.midnight_oil.operation_queue import DurableOperationQueue, provider_idempotency_key
from substrate.midnight_oil.product_path import run_authorized_job
from substrate.midnight_oil.spend_consent import SpendConsentStore
from substrate.midnight_oil.worker import FakeClock, WorkerStepResult

OWNER = "alice"
OTHER_OWNER = "mallory"
JOB_ID = "spr04-job"
HEADER = "X-Midnight-Oil-Spend-Consent"
NOW_MS = 10_000


def _paths(root: Path) -> dict[str, Path]:
    return {
        "jobs": root / "jobs.sqlite3",
        "consents": root / "consents.sqlite3",
        "queue": root / "queue.sqlite3",
        "engagement": root / "engagement",
        "budget": root / "jobs.sqlite3.budget.duckdb",
    }


def _dependencies(root: Path, key: bytes) -> MidnightOilDependencies:
    paths = _paths(root)
    return MidnightOilDependencies(
        jobs=SqliteDurableJobStore(paths["jobs"]),
        consents=SpendConsentStore(paths["consents"]),
        active_key_id="spr04-key",
        signing_key=key,
        verification_keys={"spr04-key": key},
        operation_queue=DurableOperationQueue(paths["queue"]),
        clock_ms=lambda: NOW_MS,
        random_bytes=lambda size: bytes(range(1, size + 1)),
        test_mode=True,
    )


def _client(root: Path, key: bytes) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def identify(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = request.headers.get("x-test-user", OWNER)
        return await call_next(request)

    register_midnight_oil_routes(app, _dependencies(root, key))
    return TestClient(app)


def _create_and_consent(root: Path, key: bytes) -> tuple[str, int]:
    with _client(root, key) as client:
        created = client.post(
            "/midnight-oil/create",
            headers={"x-test-user": OWNER},
            json={
                "job_id": JOB_ID,
                "asset_id": "spr04-asset",
                "goals": ["Prove durable authorization"],
                "duration_minutes": 10,
                "model_id": "fake-provider",
            },
        )
        assert created.status_code == 200, created.text
    # Restart: consent uses new app, stores, keyring, and clock objects.
    with _client(root, key) as client:
        consent = client.post(
            f"/midnight-oil/jobs/{JOB_ID}/spend-consent",
            headers={"x-test-user": OWNER},
            json={"use_recommended": True},
        )
        assert consent.status_code == 200, consent.text
        return consent.json()["token"], consent.json()["ceiling_cents"]


def _scan_surfaces(
    root: Path,
    canaries: tuple[str, ...],
    *,
    responses: tuple[str, ...] = (),
    logs: tuple[str, ...] = (),
    exceptions: tuple[str, ...] = (),
) -> None:
    persisted = "\n".join(
        path.read_bytes().decode("utf-8", "ignore")
        for path in root.rglob("*")
        if path.is_file()
    )
    openapi = _client(root, b"K" * 32).app.openapi()
    haystacks = (persisted, repr(openapi), *responses, *logs, *exceptions)
    for canary in canaries:
        assert all(canary not in haystack for haystack in haystacks), (
            f"secret canary leaked: {canary!r}"
        )


def test_restart_each_boundary_reaches_one_bounded_operation_and_durable_deposit(
    tmp_path: Path,
) -> None:
    key = b"SPR04-KEY-CANARY-UNIQUE-123456789"[:32]
    token, ceiling = _create_and_consent(tmp_path, key)

    # Restart: token claim -> owner CAS -> enqueue.
    with _client(tmp_path, key) as client:
        dispatched = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        )
        assert dispatched.status_code == 200, dispatched.text
        operation_id = dispatched.json()["operation_id"]
        assert dispatched.json()["state"] == "dispatch_claimed"

    # Restart independently at the queue -> worker boundary.
    paths = _paths(tmp_path)
    calls: list[str] = []
    provider_outputs: list[WorkerStepResult] = []

    def fake_provider(job, key_id):  # type: ignore[no-untyped-def]
        calls.append(key_id)
        result = WorkerStepResult(
            spent_usd=0.01,
            spawn_id="spr04-spawn",
            output_text="Hermetic fake-provider result",
            insights=("Durability is observable",),
            questions=("How will live billing reconcile?",),
            done=True,
        )
        provider_outputs.append(result)
        return result

    authority = SqliteDurableJobStore(paths["jobs"])
    queue = DurableOperationQueue(paths["queue"])
    final = run_authorized_job(
        operation_id,
        owner_user_id=OWNER,
        job_id=JOB_ID,
        authority_store=authority,
        operation_queue=queue,
        worker_id="spr04-worker",
        now_ms=NOW_MS + 1,
        lease_duration_ms=1_000,
        step_fn=fake_provider,
        project_fn=lambda job: 0.01,
        clock=FakeClock(NOW_MS + 1),
    )
    assert calls == [provider_idempotency_key(operation_id, 0)]
    assert final.status == "complete"
    assert round(final.spent_usd * 100) == 1 <= ceiling

    # Restart independently at worker -> ledger -> deposit.
    reopened_authority = SqliteDurableJobStore(paths["jobs"])
    execution = OwnerBoundDurableJobStore(reopened_authority, OWNER)
    engagement = FileEngagementStore(paths["engagement"])
    deposited = deposit_job_results(
        JOB_ID,
        job_store=execution,
        engagement_store=engagement,
        step_outputs=tuple(provider_outputs),
    )
    assert deposited.html.startswith("<!DOCTYPE html>")
    assert provider_outputs[0].output_text in deposited.html
    assert deposited.twin_count == 2
    assert engagement.get_document(deposited.document_id) is not None
    with sqlite3.connect(paths["queue"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT operation_id) FROM midnight_oil_operation_queue"
        ).fetchone() == (1, 1)
    budget_con = duckdb.connect(str(paths["budget"]), read_only=True)
    try:
        ledger = budget_con.execute(
            "SELECT COUNT(*) FROM midnight_oil_spend_ledger WHERE event = 'debit'"
        ).fetchone()
    finally:
        budget_con.close()
    assert ledger == (1,)
    _scan_surfaces(tmp_path, (token, base64.b64encode(key).decode()), responses=(deposited.html,))


def test_idor_is_independently_rejected_before_token_claim(tmp_path: Path) -> None:
    key = b"I" * 32
    token, _ = _create_and_consent(tmp_path, key)
    with _client(tmp_path, key) as client:
        response = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OTHER_OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        )
    assert response.status_code == 404
    assert DurableOperationQueue(_paths(tmp_path)["queue"]).get("missing") is None
    _scan_surfaces(tmp_path, (token, base64.b64encode(key).decode()), responses=(response.text,))


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("goals_json", '["altered-config"]', 403),
        ("approved_ceiling_cents", 1, 403),
        ("operation_id", "altered-operation", 403),
    ],
    ids=("altered-config", "altered-ceiling", "altered-operation"),
)
def test_token_binding_guards_bite_independently(
    tmp_path: Path, column: str, value: object, expected: int
) -> None:
    key = (column.encode() + b"X" * 32)[:32]
    token, ceiling = _create_and_consent(tmp_path, key)
    if column == "approved_ceiling_cents" and ceiling == 1:
        value = 2
    with sqlite3.connect(_paths(tmp_path)["jobs"]) as connection:
        connection.execute(
            f"UPDATE midnight_oil_jobs SET {column} = ? WHERE job_id = ?", (value, JOB_ID)
        )
    with _client(tmp_path, key) as client:
        response = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        )
    assert response.status_code == expected
    with sqlite3.connect(_paths(tmp_path)["queue"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM midnight_oil_operation_queue").fetchone() == (0,)
    _scan_surfaces(tmp_path, (token, base64.b64encode(key).decode()), responses=(response.text,))


def test_replay_storm_and_duplicate_insert_converge_to_exactly_one_row(tmp_path: Path) -> None:
    key = b"R" * 32
    token, _ = _create_and_consent(tmp_path, key)
    responses = []
    for _ in range(40):
        with _client(tmp_path, key) as client:
            responses.append(
                client.post(
                    "/midnight-oil/run",
                    headers={"x-test-user": OWNER, HEADER: token},
                    json={"job_id": JOB_ID},
                )
            )
    assert {response.status_code for response in responses} == {200}
    operation_id = responses[0].json()["operation_id"]
    queue = DurableOperationQueue(_paths(tmp_path)["queue"])
    replayed, inserted = queue.enqueue_once(
        operation_id=operation_id,
        owner_user_id=OWNER,
        job_id=JOB_ID,
        enqueued_at_ms=NOW_MS,
        options={"max_steps": None, "auto_deposit": False, "draft_combined": True, "force_offline": True},
    )
    assert inserted is False and replayed.operation_id == operation_id
    with sqlite3.connect(queue.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM midnight_oil_operation_queue").fetchone() == (1,)
    _scan_surfaces(tmp_path, (token, base64.b64encode(key).decode()), responses=tuple(r.text for r in responses))


def test_stale_authority_version_and_stale_worker_lease_each_block(tmp_path: Path) -> None:
    key = b"S" * 32
    token, _ = _create_and_consent(tmp_path, key)
    store = SqliteDurableJobStore(_paths(tmp_path)["jobs"])
    job = store.get_job_for_owner(JOB_ID, OWNER)
    assert job is not None and job.authority is not None
    stale = store.compare_and_set_authority(
        JOB_ID,
        OWNER,
        expected_version=job.authority.state_version - 1,
        expected_state="approved",
        expected_operation_id=job.authority.operation_id,
        operation_id=job.authority.operation_id,
        next_state="dispatch_claimed",
    )
    assert stale is None
    with _client(tmp_path, key) as client:
        operation_id = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        ).json()["operation_id"]
    queue = DurableOperationQueue(_paths(tmp_path)["queue"])
    old, won = queue.lease(operation_id=operation_id, worker_id="old", leased_at_ms=NOW_MS + 1, lease_expires_at_ms=NOW_MS + 5)
    _, taken = queue.lease(operation_id=operation_id, worker_id="new", leased_at_ms=NOW_MS + 6, lease_expires_at_ms=NOW_MS + 20)
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="stale"):
        queue.run_fenced(
            operation_id=operation_id,
            worker_id="old",
            lease_generation=old.lease_generation,
            now_ms=NOW_MS + 7,
            expected_step_index=0,
            action=lambda: (calls.append("provider"), True),
        )
    assert won and taken and calls == []
    _scan_surfaces(tmp_path, (token, base64.b64encode(key).decode()))


def test_provider_unknown_outcome_halts_without_redispatch_and_leaks_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key = b"U" * 32
    token, _ = _create_and_consent(tmp_path, key)
    with _client(tmp_path, key) as client:
        operation_id = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        ).json()["operation_id"]
    calls: list[str] = []
    caplog.set_level(logging.DEBUG)

    def unknown(job, key_id):  # type: ignore[no-untyped-def]
        calls.append(key_id)
        raise TimeoutError("provider outcome unknown")

    with pytest.raises(UnknownCallOutcome) as caught:
        run_authorized_job(
            operation_id,
            owner_user_id=OWNER,
            job_id=JOB_ID,
            authority_store=SqliteDurableJobStore(_paths(tmp_path)["jobs"]),
            operation_queue=DurableOperationQueue(_paths(tmp_path)["queue"]),
            worker_id="unknown-worker",
            now_ms=NOW_MS + 1,
            lease_duration_ms=1_000,
            step_fn=unknown,
            project_fn=lambda job: 0.01,
            clock=FakeClock(NOW_MS + 1),
        )
    assert isinstance(caught.value.provider_error, TimeoutError)
    reopened = SqliteDurableJobStore(_paths(tmp_path)["jobs"]).get_job_for_owner(JOB_ID, OWNER)
    assert reopened is not None and reopened.authority is not None
    assert reopened.authority.operation_state == "failed_closed"
    assert reopened.returned_step_keys == ()
    assert len(calls) == 1
    _scan_surfaces(
        tmp_path,
        (token, base64.b64encode(key).decode()),
        logs=tuple(record.getMessage() for record in caplog.records),
        exceptions=(str(caught.value),),
    )


def test_provider_exception_and_lost_authority_cas_require_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"R" * 32
    token, _ = _create_and_consent(tmp_path, key)
    with _client(tmp_path, key) as client:
        operation_id = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        ).json()["operation_id"]

    authority = SqliteDurableJobStore(_paths(tmp_path)["jobs"])
    original_cas = authority.compare_and_set_authority
    calls = 0

    def lose_exception_transition(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            return None
        return original_cas(*args, **kwargs)

    monkeypatch.setattr(authority, "compare_and_set_authority", lose_exception_transition)

    def unknown(job, key_id):  # type: ignore[no-untyped-def]
        raise TimeoutError("provider outcome unknown")

    with pytest.raises(
        RuntimeError, match="exception-path authority requires reconciliation"
    ) as caught:
        run_authorized_job(
            operation_id,
            owner_user_id=OWNER,
            job_id=JOB_ID,
            authority_store=authority,
            operation_queue=DurableOperationQueue(_paths(tmp_path)["queue"]),
            worker_id="lost-cas-worker",
            now_ms=NOW_MS + 1,
            lease_duration_ms=1_000,
            step_fn=unknown,
            project_fn=lambda job: 0.01,
            clock=FakeClock(NOW_MS + 1),
        )
    assert isinstance(caught.value.__cause__, UnknownCallOutcome)
    assert calls == 2


def test_provider_exception_preserves_concurrently_terminal_authority(tmp_path: Path) -> None:
    key = b"T" * 32
    token, _ = _create_and_consent(tmp_path, key)
    with _client(tmp_path, key) as client:
        operation_id = client.post(
            "/midnight-oil/run",
            headers={"x-test-user": OWNER, HEADER: token},
            json={"job_id": JOB_ID},
        ).json()["operation_id"]

    authority = SqliteDurableJobStore(_paths(tmp_path)["jobs"])

    def concurrently_finish_then_fail(job, key_id):  # type: ignore[no-untyped-def]
        current = authority.get_job_for_owner(JOB_ID, OWNER)
        assert current is not None and current.authority is not None
        changed = authority.compare_and_set_authority(
            JOB_ID,
            OWNER,
            expected_version=current.authority.state_version,
            expected_state="dispatch_started",
            expected_operation_id=operation_id,
            operation_id=operation_id,
            next_state="dispatch_finished",
            dispatch_completed_at_ms=NOW_MS + 2,
        )
        assert changed is not None
        raise TimeoutError("late provider observer failed")

    with pytest.raises(ValueError, match="worker cannot change durable operation authority") as caught:
        run_authorized_job(
            operation_id,
            owner_user_id=OWNER,
            job_id=JOB_ID,
            authority_store=authority,
            operation_queue=DurableOperationQueue(_paths(tmp_path)["queue"]),
            worker_id="terminal-race-worker",
            now_ms=NOW_MS + 1,
            lease_duration_ms=1_000,
            step_fn=concurrently_finish_then_fail,
            project_fn=lambda job: 0.01,
            clock=FakeClock(NOW_MS + 1),
        )
    reopened = authority.get_job_for_owner(JOB_ID, OWNER)
    assert reopened is not None and reopened.authority is not None
    assert reopened.authority.operation_state == "dispatch_finished"
    assert isinstance(caught.value.__context__, UnknownCallOutcome)


def _live_env(root: Path) -> dict[str, str]:
    key = base64.b64encode(b"P" * 32).decode()
    return {
        "ANTIEK_MIDNIGHT_OIL_DB": str(root / "jobs.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_CONSENT_DB": str(root / "consents.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_QUEUE_DB": str(root / "queue.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_ACTIVE_KEY_ID": "live-key",
        "ANTIEK_MIDNIGHT_OIL_SIGNING_KEY_B64": key,
        "ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON": json.dumps({"live-key": key}),
    }


@pytest.mark.parametrize(
    "missing",
    [
        "ANTIEK_MIDNIGHT_OIL_DB",
        "ANTIEK_MIDNIGHT_OIL_CONSENT_DB",
        "ANTIEK_MIDNIGHT_OIL_QUEUE_DB",
        "ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON",
    ],
    ids=("durable-jobs", "stable-consents", "enqueue-once-queue", "keyring"),
)
def test_live_startup_fails_closed_when_durable_dependency_is_removed(
    tmp_path: Path, missing: str
) -> None:
    env = _live_env(tmp_path)
    del env[missing]
    with pytest.raises((RuntimeError, ValueError)):
        production_dependencies_from_env(env)


@pytest.mark.parametrize("dependency", ["clock_ms", "random_bytes"], ids=("trusted-clock", "csprng"))
def test_live_startup_rejects_clock_or_rng_substitute(
    tmp_path: Path, dependency: str
) -> None:
    deps = production_dependencies_from_env(_live_env(tmp_path))
    values = {field.name: getattr(deps, field.name) for field in fields(MidnightOilDependencies)}
    values[dependency] = (lambda: 0) if dependency == "clock_ms" else (lambda size: b"x" * size)
    with pytest.raises(ValueError, match="system clock and CSPRNG"):
        MidnightOilDependencies(**values)
