from __future__ import annotations

import base64
import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import Response

import interfaces.research.api.midnight_oil_routes as midnight_oil_routes
from interfaces.research.api.midnight_oil_routes import (
    CONSENT_TTL_MS,
    MidnightOilDependencies,
    midnight_oil_enabled,
    production_dependencies_from_env,
    register_midnight_oil_routes,
)
from substrate.midnight_oil.job import MidnightOilJob
from substrate.midnight_oil.job_store import SqliteDurableJobStore
from substrate.midnight_oil.spend_consent import (
    MAX_CEILING_CENTS,
    ConsentRejected,
    ConsentRejection,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

KEY_1 = b"a" * 32
KEY_2 = b"b" * 32
CONSENT_RESPONSE_FIELDS = {
    "token",
    "operation_id",
    "ceiling_cents",
    "expires_at_ms",
    "job_id",
    "status",
    "force_below_recommended",
}
BodyFactory = Callable[[str, str], dict[str, object] | None]


class Entropy:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, size: int) -> bytes:
        self.value += 1
        return bytes([self.value]) * size


def dependencies(tmp_path: Path, **overrides: object) -> MidnightOilDependencies:
    values: dict[str, object] = {
        "jobs": SqliteDurableJobStore(str(tmp_path / "jobs.sqlite3")),
        "consents": SpendConsentStore(tmp_path / "consents.sqlite3"),
        "active_key_id": "key-1",
        "signing_key": KEY_1,
        "verification_keys": {"key-1": KEY_1},
        "clock_ms": lambda: 1_000,
        "random_bytes": Entropy(),
        "test_mode": True,
    }
    values.update(overrides)
    return MidnightOilDependencies(**values)  # type: ignore[arg-type]


def make_client(deps: MidnightOilDependencies) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def authenticated_state(request: Request, call_next):  # type: ignore[no-untyped-def]
        identity = request.headers.get("x-authenticated-test-user")
        if identity is not None:
            request.state.user_id = identity
        return await call_next(request)

    register_midnight_oil_routes(app, deps)
    return TestClient(app, raise_server_exceptions=False)


def create(client: TestClient, owner: str = "owner-a") -> str:
    response = client.post(
        "/midnight-oil/create",
        headers={"x-authenticated-test-user": owner},
        json={"goals": ["Investigate durable consent"], "duration_minutes": 30},
    )
    assert response.status_code == 200, response.text
    return cast(str, response.json()["job_id"])


def consent(client: TestClient, job_id: str, owner: str = "owner-a", **body: object) -> Response:
    payload = {"use_recommended": True, **body}
    return cast(
        Response,
        client.post(
            f"/midnight-oil/jobs/{job_id}/spend-consent",
            headers={"x-authenticated-test-user": owner},
            json=payload,
        ),
    )


def config(job: MidnightOilJob) -> JobConsentConfig:
    return JobConsentConfig(
        job_id=job.job_id,
        goals=job.goals,
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
        asset_id=job.asset_id,
    )


def test_missing_identity_and_spoofed_owner_fail_closed(tmp_path: Path) -> None:
    client = make_client(dependencies(tmp_path))
    missing = client.post(
        "/midnight-oil/create",
        json={"goals": ["g"], "duration_minutes": 1},
    )
    assert missing.status_code == 401
    for spoof in (
        {"owner_user_id": "victim"},
        {"user_id": "victim"},
    ):
        response = client.post(
            "/midnight-oil/create",
            headers={"x-authenticated-test-user": "attacker", "x-owner-user-id": "victim"},
            json={"goals": ["g"], "duration_minutes": 1, **spoof},
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/midnight-oil/jobs/{job_id}", None),
        ("post", "/midnight-oil/approve", {"job_id": "{job_id}", "use_recommended": True}),
        ("post", "/midnight-oil/run", {"job_id": "{job_id}"}),
        ("post", "/midnight-oil/deposit", {"job_id": "{job_id}"}),
        (
            "post",
            "/midnight-oil/jobs/{job_id}/spend-consent",
            {"use_recommended": True},
        ),
    ],
)
def test_every_job_path_requires_state_identity_before_dependencies(
    tmp_path: Path, method: str, path: str, body: dict[str, object] | None
) -> None:
    configured = make_client(dependencies(tmp_path))
    job_id = create(configured)
    app = FastAPI()
    register_midnight_oil_routes(app)
    unauthenticated = TestClient(app, raise_server_exceptions=False)
    concrete_body = (
        None
        if body is None
        else {key: (job_id if value == "{job_id}" else value) for key, value in body.items()}
    )
    response = unauthenticated.request(
        method,
        path.format(job_id=job_id),
        headers={"x-owner-user-id": "owner-a", "x-user-id": "owner-a"},
        json=concrete_body,
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("/midnight-oil/create", b"{"),
        ("/midnight-oil/create", b""),
        ("/midnight-oil/jobs/unknown/spend-consent", b"{"),
        ("/midnight-oil/jobs/unknown/spend-consent", b""),
        ("/midnight-oil/approve", b"{"),
        ("/midnight-oil/approve", b""),
        ("/midnight-oil/run", b"{"),
        ("/midnight-oil/run", b""),
        ("/midnight-oil/deposit", b"{"),
        ("/midnight-oil/deposit", b""),
    ],
)
@pytest.mark.parametrize("configured", [False, True])
def test_unauthenticated_malformed_bodies_are_identical_401(
    tmp_path: Path, path: str, content: bytes, configured: bool
) -> None:
    app = FastAPI()
    register_midnight_oil_routes(app, dependencies(tmp_path) if configured else None)
    response = TestClient(app, raise_server_exceptions=False).post(
        path,
        content=content,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/midnight-oil/jobs/{job_id}", None),
        ("post", "/midnight-oil/approve", {"job_id": "{job_id}"}),
        ("post", "/midnight-oil/run", {"job_id": "{job_id}"}),
        ("post", "/midnight-oil/deposit", {"job_id": "{job_id}"}),
        (
            "post",
            "/midnight-oil/jobs/{job_id}/spend-consent",
            {"use_recommended": True},
        ),
    ],
)
def test_wrong_owner_is_indistinguishable_from_unknown_job(
    tmp_path: Path, method: str, path: str, body: dict[str, object] | None
) -> None:
    client = make_client(dependencies(tmp_path))
    job_id = create(client)
    concrete_path = path.format(job_id=job_id)
    concrete_body = (
        None
        if body is None
        else {key: (job_id if value == "{job_id}" else value) for key, value in body.items()}
    )
    wrong = client.request(
        method,
        concrete_path,
        headers={
            "x-authenticated-test-user": "owner-b",
            "x-owner-user-id": "owner-a",
            "x-user-id": "owner-a",
        },
        json=concrete_body,
    )
    unknown = client.request(
        method,
        path.format(job_id="unknown"),
        headers={"x-authenticated-test-user": "owner-b"},
        json=(
            None
            if concrete_body is None
            else {
                key: ("unknown" if value == job_id else value)
                for key, value in concrete_body.items()
            }
        ),
    )
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
    assert wrong.status_code == 404


@pytest.mark.parametrize("value", [True, 1.5, 0, -1, MAX_CEILING_CENTS + 1])
def test_ceiling_requires_bounded_positive_strict_integer(tmp_path: Path, value: object) -> None:
    client = make_client(dependencies(tmp_path))
    job_id = create(client)
    response = consent(
        client,
        job_id,
        use_recommended=False,
        ceiling_cents=value,
        force_below=True,
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path_template",
    [
        "/midnight-oil/jobs/{job_id}/spend-consent",
        "/midnight-oil/approve",
    ],
)
def test_consent_validation_never_reflects_credentials_and_is_no_store(
    tmp_path: Path, path_template: str
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    source_job = create(client)
    issued = consent(client, source_job).json()
    target_job = create(client)
    path = path_template.format(job_id=target_job)
    body: dict[str, object] = {
        "use_recommended": True,
        "forbidden_credential": issued["token"],
    }
    if path_template == "/midnight-oil/approve":
        body["job_id"] = target_job
    response = client.post(
        path,
        headers={"x-authenticated-test-user": "owner-a"},
        json=body,
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    serialized = response.text
    assert issued["token"] not in serialized
    assert "forbidden_credential" in serialized
    assert '"input"' not in serialized
    assert KEY_1.decode() not in serialized


@pytest.mark.parametrize(
    ("method", "path_template", "body_factory", "expected_status"),
    [
        (
            "post",
            "/midnight-oil/create",
            lambda job_id, token: {
                "goals": ["Investigate router-wide validation hardening"],
                "duration_minutes": 30,
                "forbidden_credential": token,
            },
            422,
        ),
        (
            "get",
            "/midnight-oil/jobs/{token}",
            lambda job_id, token: None,
            404,
        ),
        (
            "post",
            "/midnight-oil/run",
            lambda job_id, token: {"job_id": job_id, "forbidden_credential": token},
            422,
        ),
        (
            "post",
            "/midnight-oil/deposit",
            lambda job_id, token: {"job_id": job_id, "forbidden_credential": token},
            422,
        ),
        (
            "post",
            "/midnight-oil/approve",
            lambda job_id, token: {
                "job_id": job_id,
                "use_recommended": True,
                "forbidden_credential": token,
            },
            422,
        ),
        (
            "post",
            "/midnight-oil/jobs/{job_id}/spend-consent",
            lambda job_id, token: {
                "use_recommended": True,
                "forbidden_credential": token,
            },
            422,
        ),
    ],
)
def test_midnight_oil_router_never_reflects_issued_tokens(
    tmp_path: Path,
    method: str,
    path_template: str,
    body_factory: BodyFactory,
    expected_status: int,
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    source_job = create(client)
    issued = consent(client, source_job).json()
    target_job = create(client)
    path = path_template.format(job_id=target_job, token=issued["token"])
    payload = body_factory(target_job, issued["token"])
    response = client.request(
        method,
        path,
        headers={"x-authenticated-test-user": "owner-a"},
        json=payload,
    )
    assert response.status_code == expected_status
    assert response.headers["cache-control"] == "no-store"
    serialized = response.text
    assert issued["token"] not in serialized
    assert '"input"' not in serialized
    assert KEY_1.decode() not in serialized
    if payload is not None and "forbidden_credential" in payload:
        assert "forbidden_credential" in serialized


def test_consent_http_failures_are_no_store(tmp_path: Path) -> None:
    client = make_client(dependencies(tmp_path))
    job_id = create(client)
    cases = [
        consent(
            client,
            job_id,
            use_recommended=False,
            ceiling_cents=1,
            force_below=False,
        ),
        consent(client, job_id, use_recommended=False),
        consent(client, job_id, owner="owner-b"),
    ]
    assert [response.status_code for response in cases] == [400, 400, 404]
    for response in cases:
        assert response.headers["cache-control"] == "no-store"
    issued = consent(client, job_id)
    assert issued.status_code == 200
    repeated = consent(client, job_id)
    assert repeated.status_code == 409
    assert repeated.headers["cache-control"] == "no-store"


def test_token_returned_once_no_store_and_safe_metadata_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    job_id = create(client)
    caplog.set_level(logging.DEBUG)
    response = consent(client, job_id)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert set(payload) == CONSENT_RESPONSE_FIELDS
    assert payload["expires_at_ms"] == 1_000 + CONSENT_TTL_MS
    assert payload["token"] not in caplog.text
    assert payload["token"] not in repr(deps)
    assert KEY_1.decode() not in repr(deps)
    assert payload["token"].encode() not in (tmp_path / "consents.sqlite3").read_bytes()
    assert payload["token"].encode() not in (tmp_path / "jobs.sqlite3").read_bytes()
    assert KEY_1 not in (tmp_path / "consents.sqlite3").read_bytes()
    assert KEY_1 not in (tmp_path / "jobs.sqlite3").read_bytes()
    assert (
        payload["token"]
        not in client.get(
            f"/midnight-oil/jobs/{job_id}",
            headers={"x-authenticated-test-user": "owner-a"},
        ).text
    )
    row = deps.jobs.get_job_for_owner(job_id, "owner-a")
    assert row is not None and row.authority is not None
    assert row.authority.operation_state == "approved"
    assert row.authority.operation_id == payload["operation_id"]
    assert row.authority.approved_ceiling_cents == payload["ceiling_cents"]
    assert row.authority.consent_granted_by_user_id == "owner-a"
    second = consent(client, job_id)
    assert second.status_code == 409
    assert "token" not in second.text


def test_cas_race_leaves_harmless_orphan_receipt(tmp_path: Path) -> None:
    inner = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite3"))

    class LosingStore:
        def put_job_for_owner(self, owner_user_id: str, job: MidnightOilJob) -> MidnightOilJob:
            return inner.put_job_for_owner(owner_user_id, job)

        def get_job_for_owner(self, job_id: str, owner_user_id: str) -> MidnightOilJob | None:
            return inner.get_job_for_owner(job_id, owner_user_id)

        def compare_and_set_authority(self, *args: object, **kwargs: object) -> None:
            return None

    deps = dependencies(tmp_path, jobs=LosingStore())
    client = make_client(deps)
    job_id = create(client)
    response = consent(client, job_id)
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    job = inner.get_job_for_owner(job_id, "owner-a")
    assert job is not None and job.authority is not None
    assert job.authority.operation_state == "awaiting_approval"
    assert job.authority.approved_ceiling_cents is None
    assert job.force_below_recommended is False
    with sqlite3.connect(tmp_path / "consents.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM spend_consents").fetchone() == (1,)


def test_rotation_expiry_unknown_key_and_bound_mutation(tmp_path: Path) -> None:
    deps = dependencies(
        tmp_path,
        active_key_id="key-2",
        signing_key=KEY_2,
        verification_keys={"key-1": KEY_1, "key-2": KEY_2},
    )
    client = make_client(deps)
    job_id = create(client)
    issued = consent(client, job_id).json()
    receipt = decode_and_verify(issued["token"], verification_keys={"key-1": KEY_1, "key-2": KEY_2})
    assert receipt.key_id == "key-2"
    with pytest.raises(ConsentRejected) as unknown:
        decode_and_verify(issued["token"], verification_keys={"key-1": KEY_1})
    assert unknown.value.reason is ConsentRejection.UNKNOWN_KEY
    job = deps.jobs.get_job_for_owner(job_id, "owner-a")
    assert job is not None
    expected = config(job)
    with pytest.raises(ConsentRejected) as expired:
        deps.consents.claim(
            issued["token"],
            expected_operator_id="owner-a",
            expected_config=expected,
            expected_operation_id=issued["operation_id"],
            expected_ceiling_cents=issued["ceiling_cents"],
            now_ms=issued["expires_at_ms"],
            verification_keys={"key-2": KEY_2},
        )
    assert expired.value.reason is ConsentRejection.EXPIRED
    mutations = [
        replace(expected, goals=("changed",)),
        replace(expected, duration_minutes=expected.duration_minutes + 1),
        replace(expected, model_id="changed"),
        replace(expected, research_tier="fast"),
        replace(expected, fanout_depth=expected.fanout_depth + 1),
        replace(expected, asset_id="changed"),
    ]
    for mutated in mutations:
        with pytest.raises(ConsentRejected) as rejected:
            deps.consents.claim(
                issued["token"],
                expected_operator_id="owner-a",
                expected_config=mutated,
                expected_operation_id=issued["operation_id"],
                expected_ceiling_cents=issued["ceiling_cents"],
                now_ms=2_000,
                verification_keys={"key-2": KEY_2},
            )
        assert rejected.value.reason is ConsentRejection.CONFIG_DRIFT

    mismatch_cases = [
        (
            "owner-b",
            expected,
            issued["operation_id"],
            issued["ceiling_cents"],
            ConsentRejection.WRONG_OPERATOR,
        ),
        (
            "owner-a",
            replace(expected, job_id="other-job"),
            issued["operation_id"],
            issued["ceiling_cents"],
            ConsentRejection.WRONG_JOB,
        ),
        (
            "owner-a",
            expected,
            "other-operation",
            issued["ceiling_cents"],
            ConsentRejection.WRONG_OPERATION,
        ),
        (
            "owner-a",
            expected,
            issued["operation_id"],
            issued["ceiling_cents"] + 1,
            ConsentRejection.CEILING_MISMATCH,
        ),
    ]
    for owner, expected_config, operation_id, ceiling_cents, reason in mismatch_cases:
        with pytest.raises(ConsentRejected) as rejected:
            deps.consents.claim(
                issued["token"],
                expected_operator_id=owner,
                expected_config=expected_config,
                expected_operation_id=operation_id,
                expected_ceiling_cents=ceiling_cents,
                now_ms=2_000,
                verification_keys={"key-2": KEY_2},
            )
        assert rejected.value.reason is reason


def test_malformed_persisted_config_fails_closed(tmp_path: Path) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    job_id = create(client)
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE midnight_oil_jobs SET goals_json = ? WHERE owner_user_id = ? AND job_id = ?",
            ('[" "]', "owner-a", job_id),
        )
    response = consent(client, job_id)
    assert response.status_code in {409, 503}
    assert response.headers["cache-control"] == "no-store"
    with sqlite3.connect(tmp_path / "consents.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM spend_consents").fetchone() == (0,)


def test_canonical_force_below_reopens_with_complete_atomic_authority(tmp_path: Path) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    job_id = create(client)
    response = consent(
        client,
        job_id,
        use_recommended=False,
        ceiling_cents=1,
        force_below=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    reopened = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite3")).get_job_for_owner(
        job_id, "owner-a"
    )
    assert reopened is not None and reopened.authority is not None
    assert reopened.status == body["status"] == "approved"
    assert reopened.authority.approved_ceiling_cents == body["ceiling_cents"] == 1
    assert reopened.authority.consent_granted_by_user_id == "owner-a"
    assert reopened.authority.operation_id == body["operation_id"]
    assert reopened.force_below_recommended is body["force_below_recommended"] is True


def test_post_cas_html_projection_failure_cannot_suppress_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    job_id = create(client)

    def fail_projection(job: MidnightOilJob) -> str:
        raise RuntimeError(f"projection unavailable for {job.job_id}")

    monkeypatch.setattr(midnight_oil_routes, "job_summary_html", fail_projection)
    response = consent(client, job_id)
    assert response.status_code == 200, response.text
    assert set(response.json()) == CONSENT_RESPONSE_FIELDS
    assert response.json()["token"]
    reopened = SqliteDurableJobStore(str(tmp_path / "jobs.sqlite3")).get_job_for_owner(
        job_id, "owner-a"
    )
    assert reopened is not None and reopened.authority is not None
    assert reopened.status == "approved"
    assert reopened.authority.operation_id == response.json()["operation_id"]


def test_live_startup_refuses_missing_and_malformed_configuration(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        production_dependencies_from_env({})
    malformed = {
        "ANTIEK_MIDNIGHT_OIL_DB": str(tmp_path / "jobs.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_CONSENT_DB": str(tmp_path / "consents.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_QUEUE_DB": str(tmp_path / "operations.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_ACTIVE_KEY_ID": "key-1",
        "ANTIEK_MIDNIGHT_OIL_SIGNING_KEY_B64": "not base64",
        "ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON": "{}",
    }
    with pytest.raises(RuntimeError):
        production_dependencies_from_env(malformed)


def test_consent_service_failure_is_sanitized_no_store(tmp_path: Path) -> None:
    class BrokenConsentStore(SpendConsentStore):
        def issue(self, **kwargs: object) -> str:
            raise RuntimeError("secret service detail must not escape")

    deps = dependencies(tmp_path, consents=BrokenConsentStore(tmp_path / "broken.sqlite3"))
    client = make_client(deps)
    response = consent(client, create(client))
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "spend consent could not be issued"}
    assert "secret service detail" not in response.text


@pytest.mark.parametrize(
    "path_factory",
    [
        lambda job_id: f"/midnight-oil/jobs/{job_id}",
        lambda job_id: f"/midnight-oil/jobs/{job_id}/spend-consent",
    ],
    ids=["read", "consent"],
)
def test_malformed_durable_row_is_generic_secret_free_no_store(
    tmp_path: Path, path_factory: Callable[[str], str]
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    job_id = create(client)
    injected_secret = "previously-issued-token.secret-credential"
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE midnight_oil_jobs SET goals_json = ? WHERE owner_user_id = ? AND job_id = ?",
            (f"not-json-{injected_secret}", "owner-a", job_id),
        )

    path = path_factory(job_id)
    response = client.request(
        "GET" if path.endswith(job_id) else "POST",
        path,
        headers={"x-authenticated-test-user": "owner-a"},
        json=None if path.endswith(job_id) else {"use_recommended": True},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Midnight Oil service unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert injected_secret not in response.text
    assert job_id not in response.text


def test_create_projection_failure_is_generic_secret_free_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = dependencies(tmp_path)
    client = make_client(deps)
    injected_secret = "request-credential-that-must-not-escape"

    def fail_projection(job: MidnightOilJob) -> str:
        raise RuntimeError(f"{injected_secret}:{job.job_id}")

    monkeypatch.setattr(midnight_oil_routes, "job_summary_html", fail_projection)
    response = client.post(
        "/midnight-oil/create",
        headers={"x-authenticated-test-user": "owner-a"},
        json={"goals": [injected_secret], "duration_minutes": 30},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Midnight Oil service unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert injected_secret not in response.text
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM midnight_oil_jobs").fetchone() == (1,)


@pytest.mark.parametrize("value", [None, "", "0", "false", "FALSE", "no", "off"])
def test_midnight_oil_enablement_explicit_false_values(value: str | None) -> None:
    assert midnight_oil_enabled(value) is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_midnight_oil_enablement_explicit_true_values(value: str) -> None:
    assert midnight_oil_enabled(value) is True


@pytest.mark.parametrize("value", ["tru", "enabled", "2", " true ", " off "])
def test_midnight_oil_enablement_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(RuntimeError, match="explicit boolean"):
        midnight_oil_enabled(value)


def test_production_key_ids_reject_noncanonical_configuration(tmp_path: Path) -> None:
    encoded = base64.b64encode(KEY_1).decode("ascii")
    base = {
        "ANTIEK_MIDNIGHT_OIL_DB": str(tmp_path / "jobs.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_CONSENT_DB": str(tmp_path / "consents.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_QUEUE_DB": str(tmp_path / "operations.sqlite3"),
        "ANTIEK_MIDNIGHT_OIL_ACTIVE_KEY_ID": "key-1",
        "ANTIEK_MIDNIGHT_OIL_SIGNING_KEY_B64": encoded,
        "ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON": json.dumps({"key-1": encoded}),
    }
    with pytest.raises(RuntimeError, match="active consent key id"):
        production_dependencies_from_env({**base, "ANTIEK_MIDNIGHT_OIL_ACTIVE_KEY_ID": " key-1 "})
    with pytest.raises(RuntimeError, match="verification key ids"):
        production_dependencies_from_env(
            {
                **base,
                "ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON": json.dumps({" key-1 ": encoded}),
            }
        )


def test_openapi_has_no_owner_or_float_approval_authority(tmp_path: Path) -> None:
    client = make_client(dependencies(tmp_path))
    document = client.get("/openapi.json").json()
    serialized = json.dumps(document)
    assert "owner_user_id" not in serialized
    assert "ceiling_usd" not in serialized
    approve_schema = document["components"]["schemas"]["LegacyApproveBody"]
    assert set(approve_schema["properties"]) == {
        "job_id",
        "ceiling_cents",
        "use_recommended",
        "force_below",
    }
    consent_schema = document["components"]["schemas"]["ConsentBody"]
    assert consent_schema["properties"]["ceiling_cents"]["anyOf"][0]["type"] == "integer"


def test_dependency_repr_and_models_do_not_expose_secrets(tmp_path: Path) -> None:
    deps = dependencies(tmp_path)
    assert KEY_1.decode() not in repr(deps)
    schemas = json.dumps(make_client(deps).get("/openapi.json").json())
    assert "signing_key" not in schemas
    assert "verification_keys" not in schemas
