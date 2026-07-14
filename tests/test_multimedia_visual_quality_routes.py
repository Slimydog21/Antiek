from __future__ import annotations

import os
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations.krea.catalog import CATALOG_DIGEST
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_visual_quality_routes import (
    MultimediaVisualQualityRuntime,
    get_multimedia_visual_quality_runtime,
    multimedia_visual_quality_router,
    multimedia_visual_quality_runtime_from_environment,
)
from substrate.multimedia.visual_quality_advisory import VisualQualityAdvisoryRegistry
from tests.test_multimedia_visual_authorization import KEY
from tests.test_multimedia_visual_candidate_materialization import NOW
from tests.test_multimedia_visual_candidate_review import _candidate


def _client(tmp_path, *, owner_id: str = "owner-1"):
    store, ready, db, candidate_id = _candidate(tmp_path)
    runtime = MultimediaVisualQualityRuntime(
        store=store,
        registry=VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY),
        clock=lambda: NOW + timedelta(minutes=1),
    )
    app = FastAPI()
    app.include_router(multimedia_visual_quality_router, prefix="/multimedia")
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: owner_id
    app.dependency_overrides[get_multimedia_visual_quality_runtime] = lambda: runtime
    return TestClient(app), ready, candidate_id


def _body(revision_id: str) -> dict[str, object]:
    return {
        "request_id": "quality-route-1",
        "expected_revision_id": revision_id,
        "disposition": "accepted",
        "prompt_fidelity": "pass",
        "technical_acceptability": "pass",
        "visual_coherence": "fail",
        "production_usable": "pass",
        "reason_codes": ["visual_incoherence"],
    }


def test_authenticated_assessment_and_owner_scoped_advisory_projection(tmp_path) -> None:
    client, ready, candidate_id = _client(tmp_path)
    root = (
        f"/multimedia/assets/{ready.asset.asset_id}/visual-candidates/"
        f"{candidate_id}/quality-assessment"
    )
    response = client.post(root, json=_body(ready.asset.revision_id))
    assert response.status_code == 200
    assert response.json()["quality_score"] == 0.75
    assert "actual_cost" not in response.text

    report = client.get(
        "/multimedia/routing-recommendations/visuals",
        params={"generation_kind": "image"},
    )
    assert report.status_code == 200
    assert report.json()["cohorts"][0]["key"]["catalog_digest"] == CATALOG_DIGEST
    payload = report.json()
    assert payload["recommendation"] is None
    assert payload["cohorts"][0]["charged_cents_total"] > 0
    assert "actual_cost" not in report.text


def test_route_rejects_caller_authority_fields_foreign_owner_and_future_cutoff(tmp_path) -> None:
    client, ready, candidate_id = _client(tmp_path, owner_id="owner-2")
    root = (
        f"/multimedia/assets/{ready.asset.asset_id}/visual-candidates/"
        f"{candidate_id}/quality-assessment"
    )
    body = _body(ready.asset.revision_id)
    body["charged_cents"] = 1
    assert client.post(root, json=body).status_code == 422
    body.pop("charged_cents")
    assert client.post(root, json=body).status_code == 409
    assert client.get(
        "/multimedia/routing-recommendations/visuals",
        params={"as_of": (NOW + timedelta(days=1)).isoformat()},
    ).status_code == 422


def test_historical_runtime_needs_no_live_krea_credential(tmp_path) -> None:
    store, _, db, _ = _candidate(tmp_path)
    os.chmod(tmp_path, 0o700)
    runtime = multimedia_visual_quality_runtime_from_environment(
        store=store,
        environ={
            "ANTIEK_MULTIMEDIA_VISUAL_QUALITY_DB_PATH": db,
            "ANTIEK_MULTIMEDIA_VISUAL_QUALITY_SIGNING_KEY_HEX": KEY.hex(),
        },
    )
    assert runtime is not None
    assert not hasattr(runtime, "client")
