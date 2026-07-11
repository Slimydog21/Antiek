"""Route tests for competition gap residual execute compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_gap_residual_execute_compose_routes import (
    register_competition_gap_residual_execute_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_gap_residual_execute_compose_routes(app)
    return TestClient(app)


def test_compose_package():
    c = _client()
    r = c.post(
        "/research/competition-residual-execute/compose",
        json={
            "residual": {
                "residual_id": "res-citation-1",
                "area": "citation_grounding",
                "competitor": "perplexity",
                "residual_text": "Span-level citations",
                "antiek_status": "behind",
                "priority": "P0",
                "execution_hint": "Wire citation spans pure modules",
            },
            "operator_ack": True,
            "proposed_owned_files": [
                "apps/reading/src/api/deepResearchCitationSpans.ts"
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["package_ready"] is True
    assert body["execution_authorized"] is False
    assert body["backlog_mutated"] is False
