"""Twin notes product path."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import (  # noqa: E402
    record_twin_product,
    twins_product_payload,
)


def test_twins_product_record_and_list():
    reset_engagement_stores()
    store = eng_mod._eng()
    empty = twins_product_payload("asset-t", store=store, include_html=True)
    assert empty["note_count"] == 0
    assert empty["view_format"] == "html"
    assert empty["html"]
    assert "application/pdf" not in empty["html"].lower()

    payload = record_twin_product(
        "asset-t",
        store=store,
        kind="insight",
        text="Attention is content-addressable routing.",
        include_html=True,
    )
    assert payload["insight_count"] == 1
    assert payload["question_count"] == 0
    assert "content-addressable" in payload["html"]

    payload2 = record_twin_product(
        "asset-t",
        store=store,
        kind="question",
        text="How does multi-head attention help?",
        include_html=True,
    )
    assert payload2["note_count"] == 2
    assert payload2["question_count"] == 1


def test_api_twins_double_run():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)

    r = client.post(
        "/engagement/twins",
        json={
            "asset_id": "paper-twin",
            "kind": "insight",
            "text": "Twin notes feed recursive prompts.",
            "include_html": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insight_count"] == 1
    assert body["view_format"] == "html"
    assert body["html"]

    g1 = client.get("/engagement/twins/paper-twin?include_html=true")
    g2 = client.get("/engagement/twins/paper-twin?include_html=true")
    assert g1.status_code == 200 and g2.status_code == 200
    assert g1.json()["note_count"] == g2.json()["note_count"] == 1
    assert g1.json()["notes"][0]["note_id"] == g2.json()["notes"][0]["note_id"]
