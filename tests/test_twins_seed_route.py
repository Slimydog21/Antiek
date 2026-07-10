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


def test_api_twins_seed_usage_has_body_inferred():
    """Residual (acw): usage_source stamps has_body from body_text honesty."""
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)

    with_body = client.post(
        "/engagement/twins/seed",
        json={
            "asset_id": "dr_body_1",
            "title": "Terminal progress",
            "body_text": "Final synthesis with real body",
            "force_offline": True,
            "usage_source": "research_progress_complete",
            "research_tier": "deep",
        },
    )
    assert with_body.status_code == 200, with_body.text
    b = with_body.json()
    assert b.get("usage_has_body") is True
    assert b.get("usage_event") is not None
    assert b["usage_event"]["has_body"] is True
    assert b["usage_event"]["outcome"] == "worked"
    assert b["usage_event"]["source"] == "research_progress_complete"

    title_only = client.post(
        "/engagement/twins/seed",
        json={
            "asset_id": "dr_title_1",
            "title": "Title only host",
            "body_text": "   ",
            "force_offline": True,
            "usage_source": "marketplace_host",
        },
    )
    assert title_only.status_code == 200, title_only.text
    t = title_only.json()
    assert t.get("usage_has_body") is False
    assert t.get("usage_event") is not None
    assert t["usage_event"]["has_body"] is False
    assert t["usage_event"]["outcome"] == "failed"

    explicit = client.post(
        "/engagement/twins/seed",
        json={
            "asset_id": "dr_explicit_1",
            "title": "Explicit override",
            "body_text": "",
            "force_offline": True,
            "usage_source": "deep_research_session",
            "has_body": True,
        },
    )
    assert explicit.status_code == 200, explicit.text
    e = explicit.json()
    assert e.get("usage_has_body") is True
    assert e["usage_event"]["has_body"] is True
    assert e["usage_event"]["outcome"] == "worked"
