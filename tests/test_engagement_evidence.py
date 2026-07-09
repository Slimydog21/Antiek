"""Evidence pack product surface (residual as)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    attach_source_references,
    evidence_pack_payload,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)


@pytest.fixture
def client():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def test_evidence_pack_with_twins_and_refs():
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="paper-e", selection_text="attention"),
        store=store,
    )
    attach_source_references(
        spawn.spawn_id,
        ["https://arxiv.org/abs/1706.03762"],
        store=store,
    )
    record_twin_insight("paper-e", "Attention is content-addressable.", store=store)
    record_twin_question("paper-e", "How does multi-head help?", store=store)
    pack = evidence_pack_payload(
        "paper-e", store=store, spawn_id=spawn.spawn_id, include_html=True
    )
    assert pack["view_format"] == "html"
    assert pack["insight_count"] == 1
    assert pack["question_count"] == 1
    assert pack["ref_count"] == 1
    assert pack["html"]
    assert "application/pdf" not in pack["html"].lower()
    assert "content-addressable" in pack["html"]
    assert "1706.03762" in pack["html"] or "arxiv" in pack["html"].lower()
    # Residual (kc): default research_tier deep when spawn reserved without tier.
    assert pack["research_tier"] == "deep"


def test_evidence_pack_surfaces_spawn_research_tier_wrestle():
    """Residual (kc): evidence pack carries reserved spawn research_tier."""
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="paper-w",
            selection_text="wrestle evidence",
            region_id="ev-w",
        ),
        store=store,
        research_tier="wrestle",
    )
    record_twin_insight("paper-w", "Wrestle insight", store=store)
    pack = evidence_pack_payload(
        "paper-w", store=store, spawn_id=spawn.spawn_id, include_html=False
    )
    assert pack["research_tier"] == "wrestle"
    assert pack["spawn_id"] == spawn.spawn_id


def test_api_evidence_pack_double_run(client):
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="asset-e", selection_text="x"),
        store=store,
    )
    record_twin_insight("asset-e", "Insight A", store=store)
    r1 = client.post(
        "/engagement/evidence-pack",
        json={
            "asset_id": "asset-e",
            "spawn_id": spawn.spawn_id,
            "include_html": True,
        },
    )
    r2 = client.post(
        "/engagement/evidence-pack",
        json={
            "asset_id": "asset-e",
            "spawn_id": spawn.spawn_id,
            "include_html": True,
        },
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["insight_count"] == r2.json()["insight_count"] == 1
    assert r1.json()["view_format"] == "html"
    assert r1.json()["html"]
