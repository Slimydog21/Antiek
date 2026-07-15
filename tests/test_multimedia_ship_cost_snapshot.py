from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from integrations.krea.client import KreaClient
from interfaces.research.api import multimedia_routes
from interfaces.research.api.multimedia_hardening_routes import (
    MultimediaHardeningRuntime,
    get_multimedia_hardening_runtime,
)
from runtime.db_lock import connect_write
from substrate.multimedia.execution_authorization import issue_async_execution_authorization
from substrate.multimedia.hardening import evaluate_multimedia_asset
from substrate.multimedia.krea_reconcile import observe_provider_job
from substrate.multimedia.provider_execution import (
    begin_reserved_provider_submission,
    bind_provider_job,
)
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
    build_multimedia_ship_cost_snapshot,
    verify_multimedia_ship_cost_snapshot,
)

KEY = b"ship-cost-provider-signing-key-32b"
SNAPSHOT_KEY = b"ship-cost-snapshot-signing-key-32"
NOW = datetime(2026, 7, 14, 6, 0, tzinfo=UTC)


class _CompletedKrea(KreaClient):
    def __init__(self, job_id: str) -> None:
        super().__init__("account:secret")
        self.job_id = job_id

    def _request(self, method: str, path: str) -> bytes:
        assert (method, path) == ("GET", f"/jobs/{self.job_id}")
        return json.dumps(
            {
                "job_id": self.job_id,
                "status": "completed",
                "created_at": "2026-07-14T06:00:00Z",
                "completed_at": "2026-07-14T06:00:02Z",
                "result": {"urls": ["https://cdn.example/result.png"]},
            }
        ).encode()


def _settled_execution(
    db_path: Path,
    *,
    owner: str = "alice",
    asset_id: str = "asset-1",
    revision_id: str = "revision-1",
    suffix: str = "one",
) -> str:
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"antiek:{suffix}"))
    authorization = issue_async_execution_authorization(
        signing_key=KEY,
        request_id=f"request-{suffix}",
        operator_id=owner,
        asset_id=asset_id,
        revision_id=revision_id,
        provider="krea",
        route_policy="balanced",
        model="imagen",
        endpoint_capability="image",
        catalog_version="v1",
        catalog_digest=hashlib.sha256(b"catalog").hexdigest(),
        quote_id=f"quote-{suffix}",
        quote_expires_at=NOW + timedelta(minutes=5),
        recovery_authority_id="recovery",
        recovery_verification_key_digest=hashlib.sha256(b"recovery").hexdigest(),
        approved_ceiling_microdollars=250_001,
        request_body_digest=hashlib.sha256(suffix.encode()).hexdigest(),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    execution, _ = begin_reserved_provider_submission(
        db_path=str(db_path), authorization=authorization, signing_key=KEY, now=NOW
    )
    bind_provider_job(
        db_path=str(db_path),
        execution_id=execution.execution_id,
        provider_job_id=job_id,
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    observe_provider_job(
        db_path=str(db_path),
        execution_id=execution.execution_id,
        client=_CompletedKrea(job_id),
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=2),
    )
    return execution.execution_id


def test_exact_revision_snapshot_is_stable_and_uses_integer_charged_cents(tmp_path: Path) -> None:
    db_path = tmp_path / "accounting.duckdb"
    execution_ids = {_settled_execution(db_path), _settled_execution(db_path, suffix="two")}
    kwargs = dict(
        db_path=str(db_path),
        signing_key=KEY,
        snapshot_key=SNAPSHOT_KEY,
        owner_id="alice",
        asset_id="asset-1",
        revision_id="revision-1",
        now=NOW + timedelta(seconds=3),
    )
    first = build_multimedia_ship_cost_snapshot(**kwargs)
    second = build_multimedia_ship_cost_snapshot(**kwargs)

    assert first == second
    assert first.charged_cents == 52
    assert {row.execution_id for row in first.executions} == execution_ids
    assert isinstance(first.executions[0].charged_cents, int)
    verify_multimedia_ship_cost_snapshot(
        first,
        snapshot_key=SNAPSHOT_KEY,
        owner_id="alice",
        asset_id="asset-1",
        revision_id="revision-1",
    )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        verify_multimedia_ship_cost_snapshot(
            first.model_copy(update={"charged_cents": 51}),
            snapshot_key=SNAPSHOT_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="revision-1",
        )


def test_snapshot_fails_closed_for_empty_scope_tamper_and_post_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "accounting.duckdb"
    _settled_execution(db_path)
    common = dict(
        db_path=str(db_path),
        signing_key=KEY,
        snapshot_key=SNAPSHOT_KEY,
        asset_id="asset-1",
        revision_id="revision-1",
        now=NOW + timedelta(seconds=3),
    )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        build_multimedia_ship_cost_snapshot(owner_id="bob", **common)
    with connect_write(str(db_path), purpose="test.cost_snapshot_tamper") as connection:
        connection.execute(
            "UPDATE multimedia_execution_authorization_claims SET signature='tampered'"
        )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        build_multimedia_ship_cost_snapshot(owner_id="alice", **common)


def test_snapshot_rejects_execution_state_after_cutoff(tmp_path: Path) -> None:
    db_path = tmp_path / "accounting.duckdb"
    _settled_execution(db_path)
    with pytest.raises(MultimediaShipCostEvidenceConflict) as caught:
        build_multimedia_ship_cost_snapshot(
            db_path=str(db_path),
            signing_key=KEY,
            snapshot_key=SNAPSHOT_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="revision-1",
            now=NOW + timedelta(seconds=1),
        )
    assert caught.value.code == "evidence_conflict"


@pytest.mark.parametrize(
    "statement",
    (
        "UPDATE multimedia_provider_executions SET record_mac=repeat('0', 64)",
        "DELETE FROM multimedia_execution_authorization_claims",
        "UPDATE midnight_oil_call_holds SET state='open'",
        "UPDATE midnight_oil_reservations SET spent_cents=spent_cents+1",
    ),
)
def test_snapshot_rejects_corrupt_or_incomplete_accounting_closure(
    tmp_path: Path, statement: str
) -> None:
    db_path = tmp_path / "accounting.duckdb"
    _settled_execution(db_path)
    with connect_write(str(db_path), purpose="test.cost_snapshot_conflict") as connection:
        connection.execute(statement)

    with pytest.raises(MultimediaShipCostEvidenceConflict):
        build_multimedia_ship_cost_snapshot(
            db_path=str(db_path),
            signing_key=KEY,
            snapshot_key=SNAPSHOT_KEY,
            owner_id="alice",
            asset_id="asset-1",
            revision_id="revision-1",
            now=NOW + timedelta(seconds=3),
        )


def test_hardening_signature_has_no_authoritative_caller_floats() -> None:
    parameters = inspect.signature(evaluate_multimedia_asset).parameters
    assert "budget_usd" not in parameters
    assert "actual_cost_usd" not in parameters


def test_hardening_api_builds_evidence_server_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    db_path = tmp_path / "accounting.duckdb"
    monkeypatch.setattr(multimedia_routes, "_STORE", store)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "alice"
        return await call_next(request)

    multimedia_routes.register_multimedia_routes(app)
    app.dependency_overrides[get_multimedia_hardening_runtime] = lambda: (
        MultimediaHardeningRuntime(
            db_path=str(db_path),
            signing_key=KEY,
            snapshot_key=SNAPSHOT_KEY,
            clock=lambda: NOW + timedelta(seconds=3),
        )
    )
    client = TestClient(app)
    created = client.post(
        "/multimedia/assets",
        json={"topic": "aircraft history", "target_minutes": 15, "mode": "audio"},
    )
    assert created.status_code == 201
    asset = created.json()["asset"]

    unavailable = client.post(f"/multimedia/assets/{asset['asset_id']}/hardening")
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"] == "evidence_unavailable"

    _settled_execution(
        db_path,
        asset_id=asset["asset_id"],
        revision_id=asset["revision_id"],
        suffix="api",
    )

    response = client.post(f"/multimedia/assets/{asset['asset_id']}/hardening")

    assert response.status_code == 200
    report = response.json()["hardening_report"]
    cost_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "cost_and_budget")
    assert cost_gate["status"] == "pass"
    assert report["cost_snapshot"]["charged_cents"] == 26
