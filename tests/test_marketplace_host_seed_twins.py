"""Marketplace host seeds engagement twins (residual bv)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    get_engagement_store,  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from interfaces.research.api.marketplace_host_routes import (  # noqa: E402
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)
from substrate.engagement_spine import list_twin_notes  # noqa: E402


def test_host_seeds_twins_by_default():
    reset_engagement_stores()
    reset_marketplace_host_store()
    app = FastAPI()

    @app.middleware("http")
    async def operator_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "__operator__"
        return await call_next(request)

    register_marketplace_host_routes(app)
    register_engagement_routes(app)
    client = TestClient(app)

    cat = client.get("/marketplace/catalog")
    assert cat.status_code == 200
    free = next(e for e in cat.json()["entries"] if e.get("is_free"))
    r = client.post(
        "/marketplace/host",
        json={
            "owner_id": "operator",
            "book_id": free["book_id"],
            "seed_twins": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owner_id"] == "__operator__"
    assert body["view_format"] == "html"
    assert body.get("twins") is not None
    assert body["twins"].get("seeded") is True
    eng = get_engagement_store(create_if_missing=True)
    notes = list_twin_notes(body["document_id"], store=eng)
    assert len(notes) >= 2


def test_host_can_skip_seed():
    reset_engagement_stores()
    reset_marketplace_host_store()
    app = FastAPI()

    @app.middleware("http")
    async def operator_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "__operator__"
        return await call_next(request)

    register_marketplace_host_routes(app)
    client = TestClient(app)
    cat = client.get("/marketplace/catalog").json()
    free = next(e for e in cat["entries"] if e.get("is_free"))
    r = client.post(
        "/marketplace/host",
        json={
            "owner_id": "operator",
            "book_id": free["book_id"],
            "seed_twins": False,
        },
    )
    assert r.status_code == 200
    assert r.json().get("twins") is None
