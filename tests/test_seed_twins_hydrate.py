"""Offline twin seed on hydrate — recursive note-taker substrate (residual bu)."""

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
from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    hydrate_reference,
    list_twin_notes,
    seed_twins_for_asset,
    spawn_from_highlight,
)


def test_seed_twins_idempotent():
    store = InMemoryEngagementStore()
    first = seed_twins_for_asset(
        "asset_x",
        store=store,
        title="Attention paper",
        body_text="Transformers dominate NLP.",
        include_html=True,
    )
    assert first["seeded"] is True
    assert first["view_format"] == "html"
    notes = list_twin_notes("asset_x", store=store)
    assert len(notes) == 2
    kinds = {n.kind for n in notes}
    assert kinds == {"insight", "question"}
    assert first["html"]
    assert "application/pdf" not in first["html"].lower()
    # Residual (la): no spawn scope → research_tier null.
    assert first.get("research_tier") is None

    second = seed_twins_for_asset(
        "asset_x", store=store, title="Attention paper"
    )
    assert second["seeded"] is False
    assert second["seed_skipped"] == "twins_already_present"
    assert len(list_twin_notes("asset_x", store=store)) == 2


def test_seed_twins_surfaces_spawn_research_tier_wrestle():
    """Residual (la): seed payload + HTML carry reserved spawn research_tier."""
    store = InMemoryEngagementStore()
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="asset_w",
            selection_text="wrestle twin seed",
            region_id="tw-w",
        ),
        store=store,
        research_tier="wrestle",
    )
    out = seed_twins_for_asset(
        "asset_w",
        store=store,
        title="Wrestle asset",
        body_text="Depth posture on recursive note-taker seed.",
        source_spawn_id=spawn.spawn_id,
        include_html=True,
    )
    assert out["seeded"] is True
    assert out["research_tier"] == "wrestle"
    assert out["source_spawn_id"] == spawn.spawn_id
    assert "tier=wrestle" in (out.get("html") or "")
    assert "application/pdf" not in (out.get("html") or "").lower()


def test_hydrate_seeds_twins_by_default():
    store = InMemoryEngagementStore()
    asset = hydrate_reference(
        "arxiv:1706.03762",
        store=store,
        include_html=True,
        seed_twins=True,
    )
    assert asset.view_format == "html"
    assert asset.twins is not None
    assert asset.twins.get("seeded") is True
    twins = list_twin_notes(asset.asset_id, store=store)
    assert len(twins) >= 2
    assert any("Seeded offline twin" in n for n in asset.notes)


def test_hydrate_can_skip_seed():
    store = InMemoryEngagementStore()
    asset = hydrate_reference(
        "arxiv:1706.03762",
        store=store,
        seed_twins=False,
    )
    assert asset.twins is None
    assert list_twin_notes(asset.asset_id, store=store) == []


def test_api_hydrate_seed_twins():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    r = client.post(
        "/engagement/hydrate-ref",
        json={
            "reference": "arxiv:1706.03762",
            "include_html": True,
            "seed_twins": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["view_format"] == "html"
    assert body.get("twins") is not None
    assert body["twins"].get("seeded") is True
    assert body["twins"].get("view_format") == "html"
