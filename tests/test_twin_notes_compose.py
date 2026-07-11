"""Red-proofs: twin compose → HTML analysis draft."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_compose_routes import (
    register_twin_notes_compose_routes,
    set_twin_notes_compose_store,
)
from substrate.twin_notes.compose import compose_analysis_html
from substrate.twin_notes.store import TwinNotesError, TwinNotesStore, TwinParentMismatch


def test_compose_same_parent_html(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("asset-1", insights=["Insight A"], questions=["Q1?"])
    b = store.record("asset-1", insights=["Insight B", "Insight A"], questions=["Q2?"])
    docs = [store.load(a.twin_id), store.load(b.twin_id)]
    draft = compose_analysis_html(docs, title="My analysis")
    assert draft.parent_asset_id == "asset-1"
    assert draft.insight_count == 2  # deduped
    assert draft.question_count == 2
    assert "<h1>My analysis</h1>" in draft.html
    assert "Insight A" in draft.html
    assert "Q1?" in draft.html
    assert "<script>" not in draft.html.lower() or "&lt;script" in draft.html


def test_compose_escapes_script(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    t = store.record(
        "asset-x",
        insights=['<script>alert("x")</script> evil'],
        questions=[],
    )
    draft = compose_analysis_html([store.load(t.twin_id)])
    assert "<script>" not in draft.html
    assert "&lt;script&gt;" in draft.html


def test_compose_cross_parent_rejected(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("p1", insights=["A"])
    b = store.record("p2", insights=["B"])
    try:
        compose_analysis_html([store.load(a.twin_id), store.load(b.twin_id)])
        raise AssertionError("expected TwinParentMismatch")
    except TwinParentMismatch:
        pass


def test_compose_empty_fails(tmp_path: Path) -> None:
    try:
        compose_analysis_html([])
        raise AssertionError("expected TwinNotesError")
    except TwinNotesError:
        pass


def test_http_compose(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("asset-1", insights=["Alpha"], questions=["Q?"])
    b = store.record("asset-1", insights=["Beta"])
    set_twin_notes_compose_store(store)
    app = FastAPI()
    register_twin_notes_compose_routes(app)
    client = TestClient(app)
    r = client.post(
        "/twins/compose",
        json={"twin_ids": [a.twin_id, b.twin_id], "title": "Draft"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insight_count"] == 2
    assert "Alpha" in body["html"]
    # cross parent 409
    c = store.record("other", insights=["X"])
    bad = client.post("/twins/compose", json={"twin_ids": [a.twin_id, c.twin_id]})
    assert bad.status_code == 409
    set_twin_notes_compose_store(None)
