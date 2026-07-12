from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_visual_authorization_routes import (
    MultimediaVisualAuthorizationRuntime,
)
from interfaces.research.api.multimedia_visual_candidate_routes import (
    MultimediaVisualCandidateRuntime,
)
from interfaces.research.api.multimedia_visual_generation_routes import (
    MultimediaVisualGenerationRuntime,
)
from interfaces.research.api.multimedia_visual_review_routes import (
    MultimediaVisualReviewRuntime,
    get_multimedia_visual_review_runtime,
    multimedia_visual_review_router,
)
from tests.test_multimedia_artifact_quarantine import PNG
from tests.test_multimedia_visual_authorization import KEY, _terms
from tests.test_multimedia_visual_candidate_materialization import NOW, Resolver, Transport
from tests.test_multimedia_visual_candidate_review import OPERATOR_KEY, _candidate


def test_preview_headers_and_attestation_safe_projection(tmp_path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    authority = MultimediaVisualAuthorizationRuntime(
        store, __import__(
            "substrate.multimedia.visual_authorization", fromlist=["VisualAuthorizationRegistry"]
        ).VisualAuthorizationRegistry(db_path=str(tmp_path / "authority.duckdb"), signing_key=KEY),
        _terms(), str(tmp_path / "authority.duckdb"), KEY,
    )
    generation = MultimediaVisualGenerationRuntime(authority, object(), db, lambda: NOW)
    candidates = MultimediaVisualCandidateRuntime(
        generation, Resolver(), Transport(), frozenset({"assets.example"}),
        str(tmp_path / "quarantine"), lambda: NOW,
    )
    runtime = MultimediaVisualReviewRuntime(candidates, OPERATOR_KEY, lambda: NOW)
    app = FastAPI()
    app.include_router(multimedia_visual_review_router, prefix="/multimedia")
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: "owner-1"
    app.dependency_overrides[get_multimedia_visual_review_runtime] = lambda: runtime
    client = TestClient(app)
    root = f"/multimedia/assets/{ready.asset.asset_id}/visual-candidates/{candidate_id}"
    preview = client.get(root + "/content", params={"revision_id": ready.asset.revision_id})
    assert preview.status_code == 200 and preview.content == PNG
    assert preview.headers["cache-control"] == "private, no-store"
    assert preview.headers["x-content-type-options"] == "nosniff"
    attested = client.post(
        root + "/attestation",
        json={
            "expected_revision_id": ready.asset.revision_id,
            "operator_acknowledged_generated_provenance": True,
        },
    )
    assert attested.status_code == 200
    assert set(attested.json()) == {"artifact_receipt_id", "reviewer_id", "attested_at"}
