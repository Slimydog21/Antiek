"""Context search over twins + source refs (residual bc)."""

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
from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from substrate.engagement_spine import (  # noqa: E402
    attach_source_references,
    record_twin_insight,
    search_engagement_context,
    spawn_from_highlight,
    HighlightSelection,
)


def test_search_finds_twin_and_ref():
    reset_engagement_stores()
    store = eng_mod._eng()
    record_twin_insight(
        "asset-s",
        "Attention is content-addressable routing for transformers.",
        store=store,
    )
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="asset-s", selection_text="sel"),
        store=store,
        research_tier="wrestle",
    )
    attach_source_references(
        spawn.spawn_id,
        ["https://arxiv.org/abs/1706.03762"],
        store=store,
    )
    payload = search_engagement_context(
        store=store,
        query="attention",
        asset_id="asset-s",
        spawn_id=spawn.spawn_id,
        include_html=True,
    )
    assert payload["hit_count"] >= 1
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    # Residual (kg): spawn research_tier on scoped intelligent search.
    assert payload["research_tier"] == "wrestle"
    kinds = {h["kind"] for h in payload["hits"]}
    assert any(k.startswith("twin_") for k in kinds)

    payload2 = search_engagement_context(
        store=store,
        query="1706.03762",
        asset_id="asset-s",
        spawn_id=spawn.spawn_id,
        include_html=True,
    )
    assert payload2["hit_count"] >= 1
    assert any(h["source"] == "source_ref" for h in payload2["hits"])


def test_api_context_search_double_run():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    client.post(
        "/engagement/twins",
        json={
            "asset_id": "a1",
            "kind": "question",
            "text": "How does recursive twin notes work?",
            "include_html": False,
        },
    )
    r1 = client.post(
        "/engagement/context-search",
        json={"query": "recursive", "asset_id": "a1", "include_html": True},
    )
    r2 = client.post(
        "/engagement/context-search",
        json={"query": "recursive", "asset_id": "a1", "include_html": True},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["hit_count"] == r2.json()["hit_count"]
    assert r1.json()["view_format"] == "html"
    assert r1.json()["html"]
