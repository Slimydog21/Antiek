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
    # Residual (ajo): depth-graph honesty fields on promote payload + HTML.
    assert p1["unique_graph_node_count"] == 1
    assert p1["unique_unit_id_count"] == 1
    assert p1["content_addressed_alignment"] is True
    assert p1["graph_node_ids"] == [p1["promoted"][0]["graph_node_id"]]
    assert p1["graph_node_ids"] == p2["graph_node_ids"]  # idempotent
    assert "Depth-graph" in (p1.get("html") or "")
    assert "content_addressed_alignment=true" in (p1.get("html") or "")
    assert p1["promoted"][0]["graph_node_id"] in (p1.get("html") or "")
    assert any("unique_nodes=1" in n for n in (p1.get("notes") or []))


def test_depth_graph_honesty_fields_pure():
    """Residual (ajt): pure helper — alignment and empty cases without I/O."""
    from substrate.engagement_spine.twin_promote import depth_graph_honesty_fields

    ok = depth_graph_honesty_fields(
        [{"graph_node_id": "n1"}, {"graph_node_id": "n1"}],  # dedupe
        [{"unit_id": "n1"}],
    )
    assert ok["graph_node_ids"] == ["n1"]
    assert ok["unique_graph_node_count"] == 1
    assert ok["unique_unit_id_count"] == 1
    assert ok["content_addressed_alignment"] is True
    mis = depth_graph_honesty_fields(
        [{"graph_node_id": "n1"}],
        [{"unit_id": "n2"}],
    )
    assert mis["content_addressed_alignment"] is False
    empty = depth_graph_honesty_fields([], [])
    assert empty["unique_graph_node_count"] == 0
    assert empty["content_addressed_alignment"] is False


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


def test_promote_context_note_ids_multi_select():
    """Residual (mx): note_ids multi-select promotes only selected twins."""
    reset_engagement_stores()
    store = eng_mod._eng()
    a = record_twin_insight(
        "asset-mx",
        "First insight for multi-select.",
        store=store,
    )
    b = record_twin_insight(
        "asset-mx",
        "Second insight left unselected.",
        store=store,
    )
    q = record_twin_question(
        "asset-mx",
        "Question also unselected?",
        store=store,
    )
    # Promote only first insight by note_id.
    only_a = twin_promote_context_payload(
        "asset-mx",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
        note_ids=[a.note_id],
    )
    assert only_a["promoted_count"] == 1
    assert only_a["note_ids"] == [a.note_id]
    assert only_a["promoted"][0]["twin_note_id"] == a.note_id
    assert "First insight" in only_a["promoted"][0]["text"]

    both = twin_promote_context_payload(
        "asset-mx",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
        note_ids=[a.note_id, q.note_id],
    )
    assert both["promoted_count"] == 2
    ids = {p["twin_note_id"] for p in both["promoted"]}
    assert a.note_id in ids
    assert q.note_id in ids
    assert b.note_id not in ids

    # Intersection: kinds=insight + note_ids including question → question dropped.
    insight_only = twin_promote_context_payload(
        "asset-mx",
        store=store,
        promote_insight_fn=_offline_promote_insight,
        promote_question_fn=_offline_promote_question,
        include_html=True,
        kinds=["insight"],
        note_ids=[a.note_id, q.note_id],
    )
    assert insight_only["promoted_count"] == 1
    assert insight_only["promoted"][0]["kind"] == "insight"


def test_api_promote_context_note_ids():
    """Residual (mx): API accepts note_ids multi-select."""
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    r1 = client.post(
        "/engagement/twins",
        json={
            "asset_id": "paper-mx",
            "kind": "insight",
            "text": "API multi-select A.",
            "include_html": False,
        },
    )
    r2 = client.post(
        "/engagement/twins",
        json={
            "asset_id": "paper-mx",
            "kind": "insight",
            "text": "API multi-select B.",
            "include_html": False,
        },
    )
    assert r1.status_code == 200 and r2.status_code == 200
    notes_a = r1.json().get("notes") or []
    assert len(notes_a) >= 1
    # Prefer the note matching text A (list may be sorted by id).
    nid = next(
        (n["note_id"] for n in notes_a if "multi-select A" in n.get("text", "")),
        notes_a[0]["note_id"],
    )
    r = client.post(
        "/engagement/twins/promote-context",
        json={
            "asset_id": "paper-mx",
            "include_html": True,
            "note_ids": [nid],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["promoted_count"] == 1
    assert body["note_ids"] == [nid]
    assert body["promoted"][0]["twin_note_id"] == nid
    assert body["view_format"] == "html"
