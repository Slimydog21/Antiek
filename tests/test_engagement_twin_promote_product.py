"""Twin promote → context product path (residual bb)."""

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
    _offline_promote_insight,
    _offline_promote_question,
)
from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from substrate.engagement_spine import (  # noqa: E402
    record_twin_insight,
    record_twin_question,
    twin_promote_context_payload,
)


def test_promote_context_empty_twins_honest():
    reset_engagement_stores()
    store = eng_mod._eng()
    payload = twin_promote_context_payload(
        "empty-asset",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
    )
    assert payload["promoted_count"] == 0
    assert payload["context_unit_count"] == 0
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    assert payload["notes"]


def test_promote_context_idempotent_double_run():
    reset_engagement_stores()
    store = eng_mod._eng()
    record_twin_insight(
        "asset-p",
        "Attention is content-addressable memory.",
        store=store,
    )
    p1 = twin_promote_context_payload(
        "asset-p",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
    )
    p2 = twin_promote_context_payload(
        "asset-p",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
    )
    assert p1["promoted_count"] == 1
    assert p2["promoted_count"] == 1
    assert p1["promoted"][0]["graph_node_id"] == p2["promoted"][0]["graph_node_id"]
    assert p1["context_units"][0]["unit_id"] == p2["context_units"][0]["unit_id"]
    assert "content-addressable" in p1["html"] or "Attention" in p1["html"]


def test_api_promote_context_double_run():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)

    # seed twin via product path
    r = client.post(
        "/engagement/twins",
        json={
            "asset_id": "paper-bb",
            "kind": "insight",
            "text": "Twin notes feed recursive research prompts.",
            "include_html": False,
        },
    )
    assert r.status_code == 200

    r1 = client.post(
        "/engagement/twins/promote-context",
        json={"asset_id": "paper-bb", "include_html": True},
    )
    r2 = client.post(
        "/engagement/twins/promote-context",
        json={"asset_id": "paper-bb", "include_html": True},
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    assert b1["promoted_count"] == b2["promoted_count"] == 1
    assert b1["view_format"] == "html"
    assert b1["html"]
    assert (
        b1["promoted"][0]["graph_node_id"] == b2["promoted"][0]["graph_node_id"]
    )
    assert b1["context_units"][0]["unit_id"] == b2["context_units"][0]["unit_id"]


def test_promote_context_kinds_filter_insights_only():
    """Residual (mq): selective promote kinds=insight skips questions."""
    reset_engagement_stores()
    store = eng_mod._eng()
    record_twin_insight(
        "asset-mq",
        "Insight about transformers.",
        store=store,
    )
    record_twin_question(
        "asset-mq",
        "What is the open question?",
        store=store,
    )
    both = twin_promote_context_payload(
        "asset-mq",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
    )
    assert both["promoted_count"] == 2
    assert set(both["kinds"]) == {"insight", "question"}

    insights = twin_promote_context_payload(
        "asset-mq",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
        kinds=["insight"],
    )
    assert insights["promoted_count"] == 1
    assert insights["kinds"] == ["insight"]
    assert insights["promoted"][0]["kind"] == "insight"
    assert "transformers" in insights["promoted"][0]["text"].lower() or (
        "transformers" in (insights.get("html") or "").lower()
    )

    questions = twin_promote_context_payload(
        "asset-mq",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
        kinds=["question"],
    )
    assert questions["promoted_count"] == 1
    assert questions["kinds"] == ["question"]
    assert questions["promoted"][0]["kind"] == "question"


def test_api_promote_context_kinds_filter():
    """Residual (mq): API accepts kinds for selective promote."""
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    assert (
        client.post(
            "/engagement/twins",
            json={
                "asset_id": "paper-mq",
                "kind": "insight",
                "text": "Selective promote insight.",
                "include_html": False,
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/engagement/twins",
            json={
                "asset_id": "paper-mq",
                "kind": "question",
                "text": "Selective promote question?",
                "include_html": False,
            },
        ).status_code
        == 200
    )
    r = client.post(
        "/engagement/twins/promote-context",
        json={
            "asset_id": "paper-mq",
            "include_html": True,
            "kinds": ["question"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["promoted_count"] == 1
    assert body["kinds"] == ["question"]
    assert body["promoted"][0]["kind"] == "question"
    assert body["view_format"] == "html"
