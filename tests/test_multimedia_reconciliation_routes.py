from __future__ import annotations

import base64
import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import substrate.multimedia.chapter_tts_production as chapter_module
from interfaces.research.api.multimedia_reconciliation_routes import (
    MultimediaReconciliationRuntime,
    RecoveredChapterAudio,
    get_multimedia_reconciliation_runtime,
    multimedia_reconciliation_runtime_from_environment,
)
from interfaces.research.api.multimedia_routes import multimedia_router, register_multimedia_routes
from runtime.db_lock import FlockWriteCoordinator
from substrate.multimedia.chapter_tts_production import (
    ChapterTTSSynthesisResult,
    get_chapter_tts_attempt,
    produce_chapter_narration,
)
from substrate.multimedia.narration_run import produce_narration_run
from substrate.multimedia.tts_reconciliation import sign_provider_recovery_evidence
from tests.test_multimedia_narration_run import (
    INTEGRITY_KEY as RUN_INTEGRITY_KEY,
)
from tests.test_multimedia_narration_run import (
    KEY as RUN_KEY,
)
from tests.test_multimedia_narration_run import (
    NOW as RUN_NOW,
)
from tests.test_multimedia_narration_run import (
    _plan as run_plan,
)
from tests.test_multimedia_narration_run import (
    _prepared as prepared_run,
)
from tests.test_multimedia_tts_reconciliation import (
    EVIDENCE_KEY,
    KEY,
    NOW,
    RECOVERY_KEY,
    ProcessCrash,
    _execution_id,
    _produce_values,
    _wav,
)


def _client(runtime: MultimediaReconciliationRuntime | None) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "operator-1")
        return await call_next(request)

    app.include_router(multimedia_router)
    if runtime is not None:
        app.dependency_overrides[get_multimedia_reconciliation_runtime] = lambda: runtime
    return TestClient(app)


def _runtime(values: dict[str, object], authorization, *, now=NOW):  # type: ignore[no-untyped-def]
    return MultimediaReconciliationRuntime(
        db_path=str(values["db_path"]),
        output_dir=str(values["output_dir"]),
        signing_key=KEY,
        recovery_key=RECOVERY_KEY,
        evidence_verification_key=EVIDENCE_KEY,
        authorization_resolver=lambda execution_id: authorization,
        recovery_evidence_resolver=lambda execution_id: (_ for _ in ()).throw(
            LookupError("provider evidence unavailable")
        ),
        clock=lambda: now,
    )


def _headers(user: str = "operator-1") -> dict[str, str]:
    return {"x-test-auth": "yes", "x-test-user": user}


def test_mounted_status_requires_auth_and_runtime(tmp_path: Path) -> None:
    unavailable = _client(None).get(
        "/multimedia/executions/mmexec_missing/tts-reconciliation", headers=_headers()
    )
    assert unavailable.status_code == 503
    unauthenticated = _client(None).get(
        "/multimedia/executions/mmexec_missing/tts-reconciliation"
    )
    assert unauthenticated.status_code == 401


def test_operator_reads_and_releases_stale_seal_without_secret_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values, _, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    monkeypatch.setattr(
        chapter_module,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(ProcessCrash()),
    )
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: ChapterTTSSynthesisResult(
                _wav(), "route-seal-crash"
            ),
        )  # type: ignore[arg-type]
    client = _client(_runtime(values, authorization, now=NOW + timedelta(minutes=10)))
    route = f"/multimedia/executions/{execution_id}/tts-reconciliation"
    status_response = client.get(route, headers=_headers())
    assert status_response.status_code == 200, status_response.text
    status_body = status_response.json()
    assert status_body["next_action"] == "release_seal"
    assert status_body["action_eligible"] is True
    for secret in (
        authorization.signature,
        RECOVERY_KEY.decode(),
        str(values["output_dir"]),
        "route-seal-crash",
    ):
        assert secret not in status_response.text
    assert client.get(route, headers=_headers("other")).status_code == 404

    released = client.post(f"{route}/actions/release_seal", headers=_headers())
    assert released.status_code == 200, released.text
    assert released.json()["attempt_status"] == "received"
    assert released.json()["parent_resume_eligible"] is True
    assert client.post(f"{route}/actions/release_seal", headers=_headers()).status_code == 409


def test_quarantine_action_is_real_and_missing_recovery_evidence_is_safe(tmp_path: Path) -> None:
    values, _, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: (_ for _ in ()).throw(ProcessCrash()),
        )  # type: ignore[arg-type]
    client = _client(_runtime(values, authorization, now=NOW + timedelta(minutes=10)))
    route = f"/multimedia/executions/{execution_id}/tts-reconciliation"
    assert client.get(route, headers=_headers()).json()["next_action"] == "quarantine_send"
    quarantined = client.post(f"{route}/actions/quarantine_send", headers=_headers())
    assert quarantined.status_code == 200, quarantined.text
    assert quarantined.json()["attempt_status"] == "outcome_unknown"
    missing = client.post(f"{route}/actions/recover_unknown", headers=_headers())
    assert missing.status_code == 409
    assert missing.json()["detail"] == "required recovery evidence is unavailable"
    attempt = get_chapter_tts_attempt(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert attempt.status == "outcome_unknown"

    recovered_at = NOW + timedelta(minutes=5)
    verified_at = NOW + timedelta(minutes=10)
    audio = _wav()
    provider_request_id = "route-recovered-job"
    signature = sign_provider_recovery_evidence(
        evidence_key=EVIDENCE_KEY,
        execution_id=execution_id,
        provider_request_id=provider_request_id,
        evidence_source="recovery-1",
        audio_bytes=audio,
        recorded_at=recovered_at,
    )
    live_runtime = MultimediaReconciliationRuntime(
        **{
            **_runtime(values, authorization, now=verified_at).__dict__,
            "recovery_evidence_resolver": lambda candidate: RecoveredChapterAudio(
                provider_request_id=provider_request_id,
                audio_bytes=audio,
                evidence_source="recovery-1",
                external_signature=signature,
                recorded_at=recovered_at,
            ),
        }
    )
    recovered = _client(live_runtime).post(
        f"{route}/actions/recover_unknown", headers=_headers()
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["attempt_status"] == "received"
    assert recovered.json()["parent_resume_eligible"] is True
    assert provider_request_id not in recovered.text


def test_environment_runtime_loads_persisted_signed_authorization(tmp_path: Path) -> None:
    values, _, authorization = _produce_values(tmp_path)
    execution_id = _execution_id(authorization)
    with pytest.raises(ProcessCrash):
        produce_chapter_narration(
            **values,
            synthesize=lambda request: (_ for _ in ()).throw(ProcessCrash()),
        )  # type: ignore[arg-type]
    with FlockWriteCoordinator(str(values["db_path"])).acquire_write_context(
        "test.persist_async_authority"
    ) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_issues ("
            "operator_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, "
            "receipt_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL, "
            "PRIMARY KEY (operator_id, request_id))"
        )
        connection.execute(
            "INSERT INTO multimedia_execution_authorization_issues VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                authorization.operator_id,
                authorization.request_id,
                "test-request-hash",
                json.dumps(authorization.to_dict(), sort_keys=True, separators=(",", ":")),
            ],
        )
    def encode(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")
    runtime = multimedia_reconciliation_runtime_from_environment(
        {
            "ANTIEK_MULTIMEDIA_RECONCILIATION_DB_PATH": str(values["db_path"]),
            "ANTIEK_MULTIMEDIA_RECONCILIATION_OUTPUT_DIR": str(values["output_dir"]),
            "ANTIEK_MULTIMEDIA_SIGNING_KEY_B64": encode(KEY),
            "ANTIEK_MULTIMEDIA_RECOVERY_KEY_B64": encode(RECOVERY_KEY),
            "ANTIEK_MULTIMEDIA_EVIDENCE_KEY_B64": encode(EVIDENCE_KEY),
        }
    )
    assert runtime is not None
    configured = MultimediaReconciliationRuntime(**{**runtime.__dict__, "clock": lambda: NOW + timedelta(minutes=10)})
    response = _client(configured).post(
        f"/multimedia/executions/{execution_id}/tts-reconciliation/actions/quarantine_send",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["attempt_status"] == "outcome_unknown"


def test_environment_runtime_is_disabled_or_fails_closed_on_partial_configuration() -> None:
    assert multimedia_reconciliation_runtime_from_environment({}) is None
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_reconciliation_runtime_from_environment(
            {"ANTIEK_MULTIMEDIA_RECONCILIATION_DB_PATH": "/tmp/only-db"}
        )
    keys = {
        "ANTIEK_MULTIMEDIA_RECONCILIATION_DB_PATH": "/tmp/runtime.duckdb",
        "ANTIEK_MULTIMEDIA_RECONCILIATION_OUTPUT_DIR": "/tmp/output",
        "ANTIEK_MULTIMEDIA_SIGNING_KEY_B64": base64.b64encode(KEY).decode("ascii"),
        "ANTIEK_MULTIMEDIA_RECOVERY_KEY_B64": base64.b64encode(RECOVERY_KEY).decode("ascii"),
        "ANTIEK_MULTIMEDIA_EVIDENCE_KEY_B64": base64.b64encode(EVIDENCE_KEY).decode("ascii"),
    }
    with pytest.raises(RuntimeError, match="provider recovery configuration is incomplete"):
        multimedia_reconciliation_runtime_from_environment(
            {**keys, "ANTIEK_MULTIMEDIA_RECOVERY_ENDPOINT": "https://recovery.example/v1"}
        )
    legacy_unbound = {
        **keys,
        "ANTIEK_MULTIMEDIA_RECOVERY_ENDPOINT": "https://recovery.example/v1",
        "ANTIEK_MULTIMEDIA_RECOVERY_TOKEN": "token",
        "ANTIEK_MULTIMEDIA_RECOVERY_ACCOUNT_SHA256": "a" * 64,
        "ANTIEK_MULTIMEDIA_RECOVERY_ALLOWED_HOST": "recovery.example",
    }
    with pytest.raises(RuntimeError, match="provider recovery configuration is incomplete"):
        multimedia_reconciliation_runtime_from_environment(legacy_unbound)
    with pytest.raises(RuntimeError, match="provider recovery configuration is invalid"):
        multimedia_reconciliation_runtime_from_environment(
            {**legacy_unbound, "ANTIEK_MULTIMEDIA_RECOVERY_OPERATOR_SHA256": "not-a-digest"}
        )


def test_registered_multimedia_routes_wire_environment_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        "ANTIEK_MULTIMEDIA_RECONCILIATION_DB_PATH": str(tmp_path / "runtime.duckdb"),
        "ANTIEK_MULTIMEDIA_RECONCILIATION_OUTPUT_DIR": str(tmp_path / "output"),
        "ANTIEK_MULTIMEDIA_SIGNING_KEY_B64": base64.b64encode(KEY).decode("ascii"),
        "ANTIEK_MULTIMEDIA_RECOVERY_KEY_B64": base64.b64encode(RECOVERY_KEY).decode("ascii"),
        "ANTIEK_MULTIMEDIA_EVIDENCE_KEY_B64": base64.b64encode(EVIDENCE_KEY).decode("ascii"),
    }.items():
        monkeypatch.setenv(name, value)
    app = FastAPI()
    register_multimedia_routes(app)
    assert get_multimedia_reconciliation_runtime in app.dependency_overrides
    runtime = app.dependency_overrides[get_multimedia_reconciliation_runtime]()
    assert isinstance(runtime, MultimediaReconciliationRuntime)


def test_parent_run_projects_blocked_children_without_cross_owner_disclosure(
    tmp_path: Path,
) -> None:
    prepared, authorizations = prepared_run()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    db_path = str(tmp_path / "run.duckdb")
    with pytest.raises(ProcessCrash):
        produce_narration_run(
            plan=run_plan(),
            prepared=prepared,
            authorizations=authorizations,
            operator_id="operator-1",
            signing_key=RUN_KEY,
            integrity_key=RUN_INTEGRITY_KEY,
            db_path=db_path,
            output_dir=str(output),
            now=RUN_NOW,
            synthesize=lambda request: (_ for _ in ()).throw(ProcessCrash()),
        )
    runtime = MultimediaReconciliationRuntime(
        db_path=db_path,
        output_dir=str(output),
        signing_key=RUN_KEY,
        recovery_key=RECOVERY_KEY,
        evidence_verification_key=EVIDENCE_KEY,
        authorization_resolver=lambda execution_id: next(iter(authorizations.values())),
        recovery_evidence_resolver=lambda execution_id: (_ for _ in ()).throw(LookupError()),
        asset_revision_resolver=lambda asset_id, operator_id: (
            prepared.revision_id
            if asset_id == prepared.asset_id and operator_id == "operator-1"
            else (_ for _ in ()).throw(LookupError())
        ),
        clock=lambda: RUN_NOW + timedelta(minutes=10),
    )
    client = _client(runtime)
    route = f"/multimedia/narration-runs/{prepared.run_id}/reconciliation"
    response = client.get(route, headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_status"] == "admitted"
    assert body["blocked_chapter_count"] == 3
    assert body["parent_resume_eligible"] is False
    assert [child["chapter_id"] for child in body["children"]] == [
        "chapter-0", "chapter-1", "chapter-2"
    ]
    assert [child["state"] for child in body["children"]] == [
        "sending", "pending", "pending"
    ]
    assert body["children"][1]["reconciliation"] is None
    assert client.get(route, headers=_headers("other")).status_code == 404

    links = client.get(
        f"/multimedia/assets/{prepared.asset_id}/reconciliation-links", headers=_headers()
    )
    assert links.status_code == 200, links.text
    links_body = links.json()
    assert links_body["asset_id"] == prepared.asset_id
    assert [row["run_id"] for row in links_body["narration_runs"]] == [prepared.run_id]
    assert len(links_body["executions"]) == 3
    assert sum(row["reconciliation_available"] for row in links_body["executions"]) == 1
    assert "reconciliation" not in links_body["executions"][0]
    other = client.get(
        f"/multimedia/assets/{prepared.asset_id}/reconciliation-links",
        headers=_headers("other"),
    )
    assert other.status_code == 404

    with FlockWriteCoordinator(db_path).acquire_write_context("test.link_bounds") as connection:
        execution_row = list(
            connection.execute(
                "SELECT * FROM multimedia_provider_executions ORDER BY execution_id LIMIT 1"
            ).fetchone()
        )
        for index in range(62):
            clone = list(execution_row)
            clone[0] = f"mmexec_overflow_{index:02d}"
            clone[1] = f"mmauth_overflow_{index:02d}"
            clone[-1] = "invalid-unread-mac"
            connection.execute(
                "INSERT INTO multimedia_provider_executions VALUES ("
                + ",".join("?" for _ in clone)
                + ")",
                clone,
            )
    bounded = client.get(
        f"/multimedia/assets/{prepared.asset_id}/reconciliation-links", headers=_headers()
    )
    assert bounded.status_code == 409

    with FlockWriteCoordinator(db_path).acquire_write_context("test.run_link_bounds") as connection:
        connection.execute(
            "DELETE FROM multimedia_provider_executions WHERE execution_id LIKE 'mmexec_overflow_%'"
        )
        run_row = list(
            connection.execute(
                "SELECT * FROM multimedia_narration_runs WHERE run_id=?", [prepared.run_id]
            ).fetchone()
        )
        for index in range(8):
            clone = list(run_row)
            clone[0] = f"mmnrun_overflow_{index:02d}"
            clone[-1] = "invalid-unread-mac"
            connection.execute(
                "INSERT INTO multimedia_narration_runs VALUES ("
                + ",".join("?" for _ in clone)
                + ")",
                clone,
            )
    run_bounded = client.get(
        f"/multimedia/assets/{prepared.asset_id}/reconciliation-links", headers=_headers()
    )
    assert run_bounded.status_code == 409
