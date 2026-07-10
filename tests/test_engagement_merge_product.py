"""Engagement merge product path — draft_combined vs into_parent (residual an)."""

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
    complete_spawn,
    merge_product_payload,
    spawn_from_highlight,
    HighlightSelection,
)


@pytest.fixture
def client():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def _complete_spawn(asset_id: str, text: str, store):
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id=asset_id, selection_text=text),
        store=store,
    )
    complete_spawn(
        spawn.spawn_id,
        output_text=f"Analysis of: {text}",
        insights=["key insight"],
        questions=["open question?"],
        store=store,
    )
    return spawn


def test_merge_product_draft_leaves_parent(client):
    store = eng_mod._eng()
    spawn = _complete_spawn("book-1", "Attention is content-addressable.", store)
    # Seed parent body for honesty check
    store.put_document(
        "book-1",
        {
            "document_id": "book-1",
            "title": "Parent book",
            "body_text": "Original parent body.",
        },
    )

    payload = merge_product_payload(
        "book-1",
        [spawn.spawn_id],
        store=store,
        mode="draft_combined",
        include_html=True,
    )
    assert payload["mode"] == "draft_combined"
    assert payload["draft_leaves_parent"] is True
    assert payload["document_id"].startswith("draft_book-1_")
    assert payload["document_id"] != "book-1"
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    assert "draft" in payload["html"].lower() or "Merge mode" in payload["html"]
    # Parent body document not switched to into_parent
    parent = store.get_document("book-1")
    assert parent is not None
    assert parent.get("body_text") == "Original parent body."
    # Draft document exists separately
    draft = store.get_document(payload["document_id"])
    assert draft is not None
    assert draft["mode"] == "draft_combined"


def test_merge_product_into_parent(client):
    store = eng_mod._eng()
    spawn = _complete_spawn("paper-x", "RAG grounds answers.", store)
    payload = merge_product_payload(
        "paper-x",
        [spawn.spawn_id],
        store=store,
        mode="into_parent",
        include_html=True,
    )
    assert payload["mode"] == "into_parent"
    assert payload["draft_leaves_parent"] is False
    assert payload["document_id"] == "paper-x"
    assert payload["view_format"] == "html"
    assert payload["html"]


def test_api_merge_draft_double_run_stable(client):
    store = eng_mod._eng()
    spawn = _complete_spawn("asset-z", "Twin notes feed recursive prompts.", store)

    r1 = client.post(
        "/engagement/merge",
        json={
            "parent_asset_id": "asset-z",
            "spawn_ids": [spawn.spawn_id],
            "mode": "draft_combined",
            "include_html": True,
        },
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["mode"] == "draft_combined"
    assert b1["draft_leaves_parent"] is True
    assert b1["document_id"].startswith("draft_asset-z_")
    assert b1["view_format"] == "html"
    assert b1["html"]

    r2 = client.post(
        "/engagement/merge",
        json={
            "parent_asset_id": "asset-z",
            "spawn_ids": [spawn.spawn_id],
            "mode": "draft_combined",
            "include_html": True,
        },
    )
    assert r2.status_code == 200
    b2 = r2.json()
    # Deterministic draft id from parent+spawn set
    assert b2["document_id"] == b1["document_id"]
    assert b2["mode"] == b1["mode"]
    assert b2["draft_leaves_parent"] is True


def test_api_merge_rejects_incomplete_spawn(client):
    r = client.post(
        "/engagement/sessions/open",
        json={"asset_id": "a", "selection_text": "incomplete only"},
    )
    assert r.status_code == 200
    sid = r.json()["spawn_id"]
    r2 = client.post(
        "/engagement/merge",
        json={
            "parent_asset_id": "a",
            "spawn_ids": [sid],
            "mode": "draft_combined",
        },
    )
    assert r2.status_code == 400
    assert "complete" in r2.text.lower() or "status" in r2.text.lower()
