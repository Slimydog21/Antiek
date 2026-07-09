"""POST /engagement/twins/seed product path (residual ch)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)


def test_api_twins_seed_idempotent():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)

    r1 = client.post(
        "/engagement/twins/seed",
        json={
            "asset_id": "analysis_doc_1",
            "title": "Written analysis",
            "body_text": "Collective findings…",
            "include_html": True,
            "force_offline": True,
        },
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["seeded"] is True
    assert b1["view_format"] == "html"
    assert b1.get("html")
    assert "application/pdf" not in b1["html"].lower()

    r2 = client.post(
        "/engagement/twins/seed",
        json={"asset_id": "analysis_doc_1", "title": "Written analysis"},
    )
    assert r2.status_code == 200
    assert r2.json()["seeded"] is False
    assert r2.json()["seed_skipped"] == "twins_already_present"
