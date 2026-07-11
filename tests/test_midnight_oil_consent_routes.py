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
from substrate.midnight_oil.job import InMemoryJobStore
from substrate.midnight_oil.job_store import (
    CompareAndSetResult,
    OperationState,
    OwnerJob,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryOwnerStore,
)
from substrate.midnight_oil.spend_consent import (
    ConsentRejected,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

KEY = b"k" * 32


def _client(tmp_path: Path) -> tuple[TestClient, MidnightOilDependencies]:
    deps = MidnightOilDependencies(
        owner_jobs=MemoryOwnerStore(),
        jobs=InMemoryJobStore(),
        consents=SpendConsentStore(tmp_path / "consents.sqlite3"),
        active_key_id="test-key",
        signing_key=KEY,
        verification_keys={"test-key": KEY},
        clock_ms=lambda: 1_000_000,
        random_token=lambda size: "operation-csprng" if size == 24 else "nonce-csprng",
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
            "job_id": "job-owned",
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
        == 409
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


def test_create_collision_cannot_overwrite_another_owner(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    original = _create(client)
    collision = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "mallory"},
        json={"goals": ["replace it"], "duration_minutes": 1, "job_id": "job-owned"},
    )
    assert collision.status_code == 400
    fetched = client.get(
        "/midnight-oil/jobs/job-owned", headers={"x-test-user": "alice"}
    ).json()
    assert fetched["goals"] == original["goals"]


def test_failed_legacy_persistence_cannot_mint_spend_authority(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)

    def fail_put(job: dict[str, object]) -> None:
        del job
        raise RuntimeError("legacy persistence unavailable")

    deps.jobs.put_job = fail_put  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="legacy persistence unavailable"):
        _create(client)
    response = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert response.status_code == 404
    assert "token" not in response.text.lower()


def test_openapi_has_no_owner_or_float_approval_authority(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    schema = client.get("/openapi.json").json()
    consent_schema = repr(
        schema["paths"]["/midnight-oil/jobs/{job_id}/spend-consent"]["post"]
    )
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
            owner_user_id="alice", job_id="broken", state_version=0,
            approved_ceiling_cents=None, consent_receipt_id=None,
            consent_config_hash=None, consent_issued_at_ms=None,
            consent_expires_at_ms=None, consent_claimed_at_ms=None,
            operation_id=None, operation_state=OperationState.NONE,
            dispatch_started_at_ms=None, dispatched_at_ms=None,
            completed_at_ms=None, payload={"goals": ["g"]},
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
    assert "token" not in response.text.lower()
