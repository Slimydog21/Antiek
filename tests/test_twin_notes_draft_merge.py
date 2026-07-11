"""Red-proofs: provisional twin draft-merge HTML."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_draft_merge_routes import (
    register_twin_notes_draft_merge_routes,
    set_twin_notes_draft_merge_store,
)
from substrate.twin_notes.draft_merge import build_draft_merge
from substrate.twin_notes.store import TwinNotesError, TwinNotesStore, TwinParentMismatch


def test_draft_merge_same_parent(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("asset-1", insights=["I1"], questions=["Q1?"])
    b = store.record("asset-1", insights=["I2", "I1"], questions=["Q2?"])
    docs = [store.load(a.twin_id), store.load(b.twin_id)]
    draft = build_draft_merge(
        parent_asset_id="asset-1",
        parent_html="<p>Parent body</p>",
        twins=docs,
        title="My draft",
        now=1_000_000.0,
    )
    assert draft.provisional is True
    assert draft.parent_asset_id == "asset-1"
    assert draft.insight_count == 2
    assert draft.question_count == 2
    assert "PROVISIONAL DRAFT" in draft.html
    assert "data-provisional=\"true\"" in draft.html
    assert "I1" in draft.html and "Q1?" in draft.html
    assert draft.draft_id.startswith("draft-")


def test_parent_script_escaped(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    t = store.record("asset-x", insights=["ok"])
    draft = build_draft_merge(
        parent_asset_id="asset-x",
        parent_html='<script>alert("x")</script>',
        twins=[store.load(t.twin_id)],
    )
    assert "<script>" not in draft.html
    assert "&lt;script&gt;" in draft.html


def test_cross_parent_rejected(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("p1", insights=["A"])
    b = store.record("p2", insights=["B"])
    try:
        build_draft_merge(
            parent_asset_id="p1",
            parent_html="body",
            twins=[store.load(a.twin_id), store.load(b.twin_id)],
        )
        raise AssertionError("expected TwinParentMismatch")
    except TwinParentMismatch:
        pass


def test_empty_twins_and_parent_fail(tmp_path: Path) -> None:
    try:
        build_draft_merge(parent_asset_id="p", parent_html="", twins=[])
        raise AssertionError("expected TwinNotesError")
    except TwinNotesError:
        pass
    store = TwinNotesStore(tmp_path)
    t = store.record("real-parent", insights=["x"])
    try:
        build_draft_merge(
            parent_asset_id="  ",
            parent_html="body",
            twins=[store.load(t.twin_id)],
        )
        raise AssertionError("expected TwinNotesError")
    except (TwinNotesError, TwinParentMismatch):
        pass

def test_draft_does_not_mutate_store_and_escapes_title(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    t = store.record("asset-1", insights=["stable"], questions=[])
    before = list(tmp_path.glob("*.json"))
    assert before
    raw_before = before[0].read_bytes()
    draft = build_draft_merge(
        parent_asset_id="asset-1",
        parent_html="body",
        twins=[store.load(t.twin_id)],
        title='</h1><script>x</script>',
    )
    assert before[0].read_bytes() == raw_before
    assert "<script>" not in draft.html
    assert "&lt;/h1&gt;" in draft.html or "&lt;script&gt;" in draft.html


def test_http_draft_merge(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("asset-1", insights=["Alpha"], questions=["Q?"])
    set_twin_notes_draft_merge_store(store)
    app = FastAPI()
    register_twin_notes_draft_merge_routes(app)
    client = TestClient(app)
    r = client.post(
        "/twins/draft-merge",
        json={
            "parent_asset_id": "asset-1",
            "parent_html": "<b>hi</b>",
            "twin_ids": [a.twin_id],
            "title": "Draft",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provisional"] is True
    assert body["insight_count"] == 1
    assert "PROVISIONAL" in body["html"]
    # cross-parent 409
    other = store.record("other", insights=["X"])
    bad = client.post(
        "/twins/draft-merge",
        json={
            "parent_asset_id": "asset-1",
            "parent_html": "x",
            "twin_ids": [a.twin_id, other.twin_id],
        },
    )
    assert bad.status_code == 409
    set_twin_notes_draft_merge_store(None)
