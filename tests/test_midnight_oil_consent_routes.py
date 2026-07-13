from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_routes import (
    MidnightOilDependencies,
    register_midnight_oil_routes,
)
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.job import InMemoryJobStore
from substrate.midnight_oil.job_store import (
    CompareAndSetResult,
    OperationState,
    OwnerJob,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryOwnerStore,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.spend_consent import (
    ConsentRejected,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

KEY = b"k" * 32


def _client(tmp_path: Path) -> tuple[TestClient, MidnightOilDependencies]:
    identifier_calls = {20: 0, 28: 0}

    def random_token(size: int) -> str:
        if size in identifier_calls:
            identifier_calls[size] += 1
            stem = "job-owned" if size == 20 else "asset-owned"
            suffix = "" if identifier_calls[size] == 1 else f"-{identifier_calls[size]}"
            return f"{stem}{suffix}"
        return "operation-csprng" if size == 24 else "nonce-csprng-value"

    deps = MidnightOilDependencies(
        owner_jobs=MemoryOwnerStore(),
        jobs=InMemoryJobStore(),
        consents=SpendConsentStore(tmp_path / "consents.sqlite3"),
        active_key_id="test-key",
        signing_key=KEY,
        verification_keys={"test-key": KEY},
        operation_queue=DurableOperationQueue(tmp_path / "operations.sqlite3"),
        engagement_store=InMemoryEngagementStore(),
        clock_ms=lambda: 1_000_000,
        random_token=random_token,
        test_mode=True,
    )
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        user = request.headers.get("x-test-user")
        if user is not None:
            request.state.user_id = user
        return await call_next(request)

    register_midnight_oil_routes(app, dependencies=deps)
    return TestClient(app), deps


def _create(client: TestClient, owner: str = "alice") -> dict[str, object]:
    response = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": owner},
        json={
            "goals": ["research carefully"],
            "duration_minutes": 30,
            "model_id": "offline-stub",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_registration_and_auth_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="configured at startup"):
        register_midnight_oil_routes(FastAPI())
    client, _ = _client(tmp_path)
    assert (
        client.post(
            "/midnight-oil/create", json={"goals": ["g"], "duration_minutes": 1}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/midnight-oil/create",
            headers={"x-test-user": "   "},
            json={"goals": ["g"], "duration_minutes": 1},
        ).status_code
        == 401
    )


def test_dependency_bundle_rejects_test_stores_and_noncanonical_keys(tmp_path: Path) -> None:
    kwargs = {
        "owner_jobs": MemoryOwnerStore(),
        "jobs": InMemoryJobStore(),
        "consents": SpendConsentStore(tmp_path / "dependency-consents.sqlite3"),
        "signing_key": KEY,
        "verification_keys": {"test-key": KEY},
    }
    with pytest.raises(ValueError, match="durable stores"):
        MidnightOilDependencies(active_key_id="test-key", **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="canonical"):
        MidnightOilDependencies(
            active_key_id=" test-key ",
            test_mode=True,
            **kwargs,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="256-bit"):
        MidnightOilDependencies(
            active_key_id="test-key",
            verification_keys={"test-key": b"short"},
            signing_key=b"short",
            owner_jobs=MemoryOwnerStore(),
            jobs=InMemoryJobStore(),
            consents=SpendConsentStore(tmp_path / "weak-consents.sqlite3"),
            test_mode=True,
        )


def test_live_app_enablement_refuses_missing_or_invalid_dependencies() -> None:
    from interfaces.research.api.app import create_app

    with pytest.raises(RuntimeError, match="validated durable dependencies"):
        create_app(enable_midnight_oil=True)
    with pytest.raises(RuntimeError, match="validated durable dependencies"):
        create_app(enable_midnight_oil=True, midnight_oil_dependencies=object())


def test_owner_matrix_and_legacy_approval_contract(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    _create(client)
    wrong = {"x-test-user": "mallory"}
    assert client.get("/midnight-oil/jobs/job-owned", headers=wrong).status_code == 404
    assert (
        client.post(
            "/midnight-oil/approve", headers=wrong, json={"job_id": "job-owned"}
        ).status_code
        == 404
    )
    assert (
        client.post("/midnight-oil/run", headers=wrong, json={"job_id": "job-owned"}).status_code
        == 404
    )
    assert (
        client.post(
            "/midnight-oil/deposit", headers=wrong, json={"job_id": "job-owned"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/midnight-oil/jobs/job-owned/spend-consent",
            headers=wrong,
            json={"use_recommended": True},
        ).status_code
        == 404
    )

    own = {"x-test-user": "alice"}
    assert client.get("/midnight-oil/jobs/job-owned", headers=own).status_code == 200
    assert (
        client.post("/midnight-oil/approve", headers=own, json={"job_id": "job-owned"}).status_code
        == 410
    )
    assert (
        client.post("/midnight-oil/run", headers=own, json={"job_id": "job-owned"}).status_code
        == 400
    )
    assert (
        client.post(
            "/midnight-oil/approve", headers=own, json={"job_id": "job-owned", "ceiling_usd": 1.0}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/midnight-oil/jobs/job-owned", None),
        ("post", "/midnight-oil/approve", {"job_id": "job-owned"}),
        ("post", "/midnight-oil/run", {"job_id": "job-owned"}),
        ("post", "/midnight-oil/deposit", {"job_id": "job-owned"}),
        ("post", "/midnight-oil/jobs/job-owned/spend-consent", {"use_recommended": True}),
    ],
)
def test_every_job_route_rejects_missing_identity(
    tmp_path: Path, method: str, path: str, body: dict[str, object] | None
) -> None:
    client, _ = _client(tmp_path)
    _create(client)
    response = client.request(method, path, json=body)
    assert response.status_code == 401


def test_create_rejects_caller_controlled_identifiers(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    original = _create(client)
    collision = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "mallory"},
        json={"goals": ["replace it"], "duration_minutes": 1, "job_id": "job-owned"},
    )
    assert collision.status_code == 422
    fetched = client.get("/midnight-oil/jobs/job-owned", headers={"x-test-user": "alice"}).json()
    assert fetched["goals"] == original["goals"]


def test_failed_legacy_persistence_cannot_mint_spend_authority(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)

    def fail_put(job: dict[str, object]) -> None:
        del job
        raise RuntimeError("legacy persistence unavailable")

    deps.jobs.put_job = fail_put  # type: ignore[method-assign]
    failed = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["research carefully"], "duration_minutes": 30},
    )
    assert failed.status_code == 503
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert response.status_code == 404
    assert "token" not in response.text.lower()


def test_ambiguous_legacy_commit_never_deletes_owner_authority(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    original_put = deps.jobs.put_job

    def commit_then_raise(job: dict[str, object]) -> None:
        original_put(job)
        raise RuntimeError("connection failed after commit")

    deps.jobs.put_job = commit_then_raise  # type: ignore[method-assign]
    response = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["research carefully"], "duration_minutes": 30},
    )
    assert response.status_code == 503
    assert deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned") is not None
    assert deps.jobs.get_job("job-owned") is not None


def test_legacy_config_drift_cannot_mint_spend_authority(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    _create(client)
    legacy = deps.jobs.get_job("job-owned")
    assert legacy is not None
    legacy["goals"] = ["different execution"]
    legacy["asset_id"] = "victim-asset"
    deps.jobs.put_job(legacy)
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert response.status_code == 409
    assert "reconciliation" in response.text
    assert "token" not in response.text.lower()


def test_openapi_has_no_owner_or_float_approval_authority(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    schema = client.get("/openapi.json").json()
    consent_schema = repr(schema["paths"]["/midnight-oil/jobs/{job_id}/spend-consent"]["post"])
    approve_schema = repr(schema["paths"]["/midnight-oil/approve"]["post"])
    assert "owner" not in consent_schema.lower()
    assert "ceiling_usd" not in approve_schema


@pytest.mark.parametrize("value", [True, 1.5, -1, 0, 1_000_000_001])
def test_ceiling_cents_rejects_noncanonical_values(tmp_path: Path, value: object) -> None:
    client, _ = _client(tmp_path)
    _create(client)
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"ceiling_cents": value, "force_below": True},
    )
    assert response.status_code == 422


def test_consent_is_bound_published_and_returned_once_no_store(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client, deps = _client(tmp_path)
    created = _create(client)
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    token = body.pop("token")
    assert token and token not in repr(deps.owner_jobs)
    row = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert row is not None
    assert row.operation_id == "operation-csprng"
    assert row.consent_issued_at_ms == 1_000_000
    assert row.consent_expires_at_ms == 1_900_000
    assert token not in repr(row)
    assert token not in caplog.text
    assert token not in created["html"]
    assert body["ceiling_cents"] == int(float(created["recommended_price_ceiling_usd"]) * 100)
    assert (
        client.post(
            "/midnight-oil/jobs/job-owned/spend-consent",
            headers={"x-test-user": "alice"},
            json={"use_recommended": True},
        ).status_code
        == 409
    )
    with sqlite3.connect(tmp_path / "consents.sqlite3") as connection:
        stored = repr(connection.execute("SELECT * FROM spend_consents").fetchall())
    assert token not in stored
    conflict = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert token not in conflict.text


def test_owner_can_reset_only_unclaimed_undelivered_consent(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    _create(client)
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert issued.status_code == 200
    before = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert before is not None

    reset = client.delete(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.headers["cache-control"] == "no-store"
    assert reset.json() == {
        "schema_version": 1,
        "job_id": "job-owned",
        "state": "consent_required",
        "operation_state": "none",
        "state_version": before.state_version + 1,
        "operator_action": "issue_consent",
    }
    after = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert after is not None
    assert after.operation_state is OperationState.NONE
    assert after.operation_id is None
    assert after.approved_ceiling_cents is None
    assert after.consent_receipt_id is None
    assert after.consent_config_hash is None
    assert after.consent_issued_at_ms is None
    assert after.consent_expires_at_ms is None
    status = client.get(
        "/midnight-oil/jobs/job-owned/status",
        headers={"x-test-user": "alice"},
    )
    assert status.status_code == 200
    assert (status.json()["state"], status.json()["operator_action"]) == (
        "consent_required",
        "issue_consent",
    )


def test_reset_is_owner_isolated_and_old_token_cannot_enqueue(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    _create(client)
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    ).json()
    foreign = client.delete(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "mallory"},
    )
    assert foreign.status_code == 404
    reset = client.delete(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
    )
    assert reset.status_code == 200
    stale = client.post(
        "/midnight-oil/run",
        headers={
            "x-test-user": "alice",
            "X-Midnight-Oil-Spend-Consent": issued["token"],
        },
        json={"job_id": "job-owned"},
    )
    assert stale.status_code == 409
    assert deps.operation_queue is not None
    assert deps.operation_queue.get(issued["operation_id"]) is None


def test_reset_refuses_any_existing_queue_delivery(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    _create(client)
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    ).json()
    assert deps.operation_queue is not None
    deps.operation_queue.enqueue_once(
        operation_id=issued["operation_id"],
        owner_user_id="alice",
        job_id="job-owned",
        enqueued_at_ms=1_000_001,
        options={
            "max_steps": None,
            "auto_deposit": False,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    refused = client.delete(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
    )
    assert refused.status_code == 409
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert authority.operation_state is OperationState.CONSENT_ISSUED
    assert authority.operation_id == issued["operation_id"]


def test_reset_cas_race_has_one_winner_and_never_reopens_twice(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client, deps = _client(tmp_path)
    _create(client)
    client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )

    def revoke() -> int:
        return client.delete(
            "/midnight-oil/jobs/job-owned/spend-consent",
            headers={"x-test-user": "alice"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: revoke(), range(2)))
    assert statuses == [200, 409]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert authority.operation_state is OperationState.NONE
    assert authority.state_version == 2


def test_reset_racing_claim_and_enqueue_converges_without_orphan(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client, deps = _client(tmp_path)
    _create(client)
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    ).json()

    def revoke() -> tuple[str, int]:
        response = client.delete(
            "/midnight-oil/jobs/job-owned/spend-consent",
            headers={"x-test-user": "alice"},
        )
        return "reset", response.status_code

    def enqueue() -> tuple[str, int]:
        response = client.post(
            "/midnight-oil/run",
            headers={
                "x-test-user": "alice",
                "X-Midnight-Oil-Spend-Consent": issued["token"],
            },
            json={"job_id": "job-owned"},
        )
        return "run", response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fn) for fn in (revoke, enqueue)]
        outcomes = dict(future.result() for future in futures)
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert deps.operation_queue is not None
    delivery = deps.operation_queue.get(issued["operation_id"])
    if outcomes["reset"] == 200:
        assert outcomes["run"] == 409
        assert authority.operation_state is OperationState.NONE
        assert delivery is None
    else:
        assert outcomes == {"reset": 409, "run": 200}
        assert authority.operation_state is OperationState.QUEUED
        assert delivery is not None


def test_receipt_rejects_each_bound_config_mutation_and_key_time_failures(
    tmp_path: Path,
) -> None:
    client, deps = _client(tmp_path)
    _create(client)
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    body = response.json()
    token = body["token"]
    row = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert row is not None
    config = JobConsentConfig(
        job_id=row.job_id,
        goals=tuple(row.payload["goals"]),
        duration_minutes=row.payload["duration_minutes"],
        model_id=row.payload["model_id"],
        research_tier=row.payload["research_tier"],
        fanout_depth=row.payload["fanout_depth"],
        asset_id=row.payload["asset_id"],
    )
    receipt = decode_and_verify(token, verification_keys={"test-key": KEY})
    deps.consents.claim(
        token,
        expected_operator_id="alice",
        expected_config=config,
        expected_operation_id=body["operation_id"],
        expected_ceiling_cents=body["ceiling_cents"],
        now_ms=receipt.issued_at_ms,
        verification_keys={"test-key": KEY},
    )
    mutations = (
        replace(config, job_id="other"),
        replace(config, goals=("other",)),
        replace(config, duration_minutes=31),
        replace(config, model_id="other"),
        replace(config, research_tier="fast"),
        replace(config, fanout_depth=4),
        replace(config, asset_id="other"),
    )
    for mutated in mutations:
        with pytest.raises(ConsentRejected):
            deps.consents.claim(
                token,
                expected_operator_id="alice",
                expected_config=mutated,
                expected_operation_id=body["operation_id"],
                expected_ceiling_cents=body["ceiling_cents"],
                now_ms=receipt.issued_at_ms,
                verification_keys={"test-key": KEY},
            )
    with pytest.raises(ConsentRejected):
        decode_and_verify(token, verification_keys={"previous-key": b"p" * 32})
    assert (
        decode_and_verify(
            token,
            verification_keys={"previous-key": b"p" * 32, "test-key": KEY},
        ).receipt_id
        == receipt.receipt_id
    )
    with pytest.raises(ConsentRejected):
        deps.consents.claim(
            token,
            expected_operator_id="alice",
            expected_config=config,
            expected_operation_id=body["operation_id"],
            expected_ceiling_cents=body["ceiling_cents"],
            now_ms=receipt.expires_at_ms,
            verification_keys={"test-key": KEY},
        )


def test_malformed_persisted_config_and_error_surfaces_do_not_leak(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client, deps = _client(tmp_path)
    deps.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="alice",
            job_id="broken",
            state_version=0,
            approved_ceiling_cents=None,
            consent_receipt_id=None,
            consent_config_hash=None,
            consent_issued_at_ms=None,
            consent_expires_at_ms=None,
            consent_claimed_at_ms=None,
            operation_id=None,
            operation_state=OperationState.NONE,
            dispatch_started_at_ms=None,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={"goals": ["g"]},
        )
    )
    response = client.post(
        "/midnight-oil/jobs/broken/spend-consent",
        headers={"x-test-user": "alice"},
        json={"ceiling_cents": 1, "force_below": True},
    )
    assert response.status_code == 409
    assert "token" not in response.text.lower()
    assert "signing" not in caplog.text.lower()


def test_cas_failure_returns_no_token_and_only_orphan_receipt(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    _create(client)

    def lose_cas(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return CompareAndSetResult(applied=False, job=None)

    deps.owner_jobs.publish_consent = lose_cas  # type: ignore[method-assign]
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert "token" not in response.text.lower()
